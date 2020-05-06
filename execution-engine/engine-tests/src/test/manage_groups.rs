use assert_matches::assert_matches;
use engine_core::{engine_state::Error, execution};
use engine_test_support::{
    internal::{
        DeployItemBuilder, ExecuteRequestBuilder, InMemoryWasmTestBuilder, DEFAULT_PAYMENT,
        DEFAULT_RUN_GENESIS_REQUEST,
    },
    DEFAULT_ACCOUNT_ADDR,
};
use lazy_static::lazy_static;
use std::{collections::BTreeSet, iter::FromIterator};
use types::{
    contract_header, contract_header::MAX_GROUP_UREFS, runtime_args, Group, Key, RuntimeArgs,
    SemVer,
};

const CONTRACT_GROUPS: &str = "manage_groups.wasm";
const METADATA_HASH_KEY: &str = "metadata_hash_key";
const METADATA_ACCESS_KEY: &str = "metadata_access_key";
const CREATE_GROUPS: &str = "create_groups";
const REMOVE_GROUP: &str = "remove_group";
const EXTEND_GROUP_UREFS: &str = "extend_group_urefs";
const REMOVE_GROUP_UREFS: &str = "remove_group_urefs";
const GROUP_NAME_ARG: &str = "group_name";
const UREFS_ARG: &str = "urefs";
const NEW_UREFS_COUNT: u64 = 3;
const GROUP_1_NAME: &str = "Group 1";
const TOTAL_NEW_UREFS_ARG: &str = "total_new_urefs";
const TOTAL_GROUPS_ARG: &str = "total_groups";
const TOTAL_EXISTING_UREFS_ARG: &str = "total_existing_urefs";

lazy_static! {
    static ref DEFAULT_CREATE_GROUPS_ARGS: RuntimeArgs = runtime_args! {
        TOTAL_GROUPS_ARG => 1u64,
        TOTAL_NEW_UREFS_ARG => 1u64,
        TOTAL_EXISTING_UREFS_ARG => 1u64,
    };
}

#[ignore]
#[test]
fn should_create_and_remove_group() {
    // This test runs a contract that's after every call extends the same key with
    // more data
    let exec_request_1 =
        ExecuteRequestBuilder::standard(DEFAULT_ACCOUNT_ADDR, CONTRACT_GROUPS, ()).build();

    let mut builder = InMemoryWasmTestBuilder::default();

    builder.run_genesis(&DEFAULT_RUN_GENESIS_REQUEST);

    builder.exec(exec_request_1).expect_success().commit();

    let account = builder
        .query(None, Key::Account(DEFAULT_ACCOUNT_ADDR), &[])
        .expect("should query account")
        .as_account()
        .cloned()
        .expect("should be account");

    let metadata_hash = account
        .named_keys()
        .get(METADATA_HASH_KEY)
        .expect("should have contract metadata");
    let _access_uref = account
        .named_keys()
        .get(METADATA_ACCESS_KEY)
        .expect("should have metadata hash");

    let exec_request_2 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                CREATE_GROUPS,
                DEFAULT_CREATE_GROUPS_ARGS.clone(),
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([3; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_2).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    assert_eq!(contract_metadata.groups().len(), 1);
    let group_1 = contract_metadata
        .groups()
        .get(&Group::new(GROUP_1_NAME))
        .expect("should have group");
    assert_eq!(group_1.len(), 2);

    let exec_request_3 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let args = runtime_args! {
            GROUP_NAME_ARG => GROUP_1_NAME,
        };
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                REMOVE_GROUP,
                args,
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([3; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_3).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    assert_eq!(
        contract_metadata.groups().get(&Group::new(GROUP_1_NAME)),
        None
    );
}

#[ignore]
#[test]
fn should_create_and_extend_user_group() {
    // This test runs a contract that's after every call extends the same key with
    // more data
    let exec_request_1 =
        ExecuteRequestBuilder::standard(DEFAULT_ACCOUNT_ADDR, CONTRACT_GROUPS, ()).build();

    let mut builder = InMemoryWasmTestBuilder::default();

    builder.run_genesis(&DEFAULT_RUN_GENESIS_REQUEST);

    builder.exec(exec_request_1).expect_success().commit();

    let account = builder
        .query(None, Key::Account(DEFAULT_ACCOUNT_ADDR), &[])
        .expect("should query account")
        .as_account()
        .cloned()
        .expect("should be account");

    let metadata_hash = account
        .named_keys()
        .get(METADATA_HASH_KEY)
        .expect("should have contract metadata");
    let _access_uref = account
        .named_keys()
        .get(METADATA_ACCESS_KEY)
        .expect("should have metadata hash");

    let exec_request_2 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                CREATE_GROUPS,
                DEFAULT_CREATE_GROUPS_ARGS.clone(),
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([5; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_2).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    assert_eq!(contract_metadata.groups().len(), 1);
    let group_1 = contract_metadata
        .groups()
        .get(&Group::new(GROUP_1_NAME))
        .expect("should have group");
    assert_eq!(group_1.len(), 2);

    let exec_request_3 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let args = runtime_args! {
            GROUP_NAME_ARG => GROUP_1_NAME,
            TOTAL_NEW_UREFS_ARG => NEW_UREFS_COUNT,
        };
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                EXTEND_GROUP_UREFS,
                args,
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([3; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_3).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    let group_1_extended = contract_metadata
        .groups()
        .get(&Group::new(GROUP_1_NAME))
        .expect("should have group");
    assert!(group_1_extended.len() > group_1.len());
    // Calculates how many new urefs were created
    let new_urefs = BTreeSet::from_iter(group_1_extended.difference(&group_1));
    assert_eq!(new_urefs.len(), NEW_UREFS_COUNT as usize);
}

#[ignore]
#[test]
fn should_create_and_remove_urefs_from_group() {
    // This test runs a contract that's after every call extends the same key with
    // more data
    let exec_request_1 =
        ExecuteRequestBuilder::standard(DEFAULT_ACCOUNT_ADDR, CONTRACT_GROUPS, ()).build();

    let mut builder = InMemoryWasmTestBuilder::default();

    builder.run_genesis(&DEFAULT_RUN_GENESIS_REQUEST);

    builder.exec(exec_request_1).expect_success().commit();

    let account = builder
        .query(None, Key::Account(DEFAULT_ACCOUNT_ADDR), &[])
        .expect("should query account")
        .as_account()
        .cloned()
        .expect("should be account");

    let metadata_hash = account
        .named_keys()
        .get(METADATA_HASH_KEY)
        .expect("should have contract metadata");
    let _access_uref = account
        .named_keys()
        .get(METADATA_ACCESS_KEY)
        .expect("should have metadata hash");

    let exec_request_2 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                CREATE_GROUPS,
                DEFAULT_CREATE_GROUPS_ARGS.clone(),
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([3; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_2).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    assert_eq!(contract_metadata.groups().len(), 1);
    let group_1 = contract_metadata
        .groups()
        .get(&Group::new(GROUP_1_NAME))
        .expect("should have group");
    assert_eq!(group_1.len(), 2);

    let urefs_to_remove = Vec::from_iter(group_1.to_owned());

    let exec_request_3 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let args = runtime_args! {
            GROUP_NAME_ARG => GROUP_1_NAME,
            UREFS_ARG => urefs_to_remove,
        };
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                REMOVE_GROUP_UREFS,
                args,
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([3; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_3).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    let group_1_modified = contract_metadata
        .groups()
        .get(&Group::new(GROUP_1_NAME))
        .expect("should have group 1");
    assert!(group_1_modified.len() < group_1.len());
}

#[ignore]
#[test]
fn should_limit_max_urefs_while_extending() {
    // This test runs a contract that's after every call extends the same key with
    // more data
    let exec_request_1 =
        ExecuteRequestBuilder::standard(DEFAULT_ACCOUNT_ADDR, CONTRACT_GROUPS, ()).build();

    let mut builder = InMemoryWasmTestBuilder::default();

    builder.run_genesis(&DEFAULT_RUN_GENESIS_REQUEST);

    builder.exec(exec_request_1).expect_success().commit();

    let account = builder
        .query(None, Key::Account(DEFAULT_ACCOUNT_ADDR), &[])
        .expect("should query account")
        .as_account()
        .cloned()
        .expect("should be account");

    let metadata_hash = account
        .named_keys()
        .get(METADATA_HASH_KEY)
        .expect("should have contract metadata");
    let _access_uref = account
        .named_keys()
        .get(METADATA_ACCESS_KEY)
        .expect("should have metadata hash");

    let exec_request_2 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                CREATE_GROUPS,
                DEFAULT_CREATE_GROUPS_ARGS.clone(),
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([3; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_2).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    assert_eq!(contract_metadata.groups().len(), 1);
    let group_1 = contract_metadata
        .groups()
        .get(&Group::new(GROUP_1_NAME))
        .expect("should have group");
    assert_eq!(group_1.len(), 2);

    let exec_request_3 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let args = runtime_args! {
            GROUP_NAME_ARG => GROUP_1_NAME,
            TOTAL_NEW_UREFS_ARG => 8u64,
        };
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                EXTEND_GROUP_UREFS,
                args,
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([5; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    let exec_request_4 = {
        // This inserts metadata as an argument because this test
        // can work from different accounts which might not have the same keys in their session
        // code.
        let args = runtime_args! {
            GROUP_NAME_ARG => GROUP_1_NAME,
            // Exceeds by 1
            TOTAL_NEW_UREFS_ARG => 1u64,
        };
        let deploy = DeployItemBuilder::new()
            .with_address(DEFAULT_ACCOUNT_ADDR)
            .with_stored_versioned_contract_by_name(
                METADATA_HASH_KEY,
                SemVer::V1_0_0,
                EXTEND_GROUP_UREFS,
                args,
            )
            .with_empty_payment_bytes((*DEFAULT_PAYMENT,))
            .with_authorization_keys(&[DEFAULT_ACCOUNT_ADDR])
            .with_deploy_hash([32; 32])
            .build();

        ExecuteRequestBuilder::new().push_deploy(deploy).build()
    };

    builder.exec(exec_request_3).expect_success().commit();

    let query_result = builder
        .query(None, *metadata_hash, &[])
        .expect("should have result");
    let contract_metadata = query_result
        .as_contract_metadata()
        .expect("should be metadata");
    let group_1_modified = contract_metadata
        .groups()
        .get(&Group::new(GROUP_1_NAME))
        .expect("should have group 1");
    assert_eq!(group_1_modified.len(), MAX_GROUP_UREFS as usize);

    // Tries to exceed the limit by 1
    builder.exec(exec_request_4).commit();

    let response = builder
        .get_exec_responses()
        .last()
        .expect("should have last response");
    assert_eq!(response.len(), 1);
    let exec_response = response.last().expect("should have response");
    let error = exec_response.as_error().expect("should have error");
    let error = assert_matches!(error, Error::Exec(execution::Error::Revert(e)) => e);
    assert_eq!(error, &contract_header::Error::MaxTotalURefsExceeded.into());
}
