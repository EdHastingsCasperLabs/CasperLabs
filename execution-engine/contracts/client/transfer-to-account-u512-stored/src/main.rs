#![no_std]
#![no_main]

#[macro_use]
extern crate alloc;

use alloc::{collections::BTreeMap, string::String};

use contract::{
    contract_api::{runtime, storage},
    unwrap_or_revert::UnwrapOrRevert,
};
use types::{
    account::PublicKey, CLType, CLTyped, ContractHash, EntryPoint, EntryPointAccess,
    EntryPointType, EntryPoints, Key, Parameter,
};

const DESTINATION_HASH: &str = "hash";
const DESTINATION_UREF: &str = "uref";
const PAY_FUNCTION_NAME: &str = "pay";
const STANDARD_PAYMENT_CONTRACT_NAME: &str = "standard_payment";

const CONTRACT_NAME: &str = "transfer_to_account";
const FUNCTION_NAME: &str = "transfer";
const ARG_TARGET: &str = "target";
const ARG_AMOUNT: &str = "amount";

#[no_mangle]
pub extern "C" fn transfer() {
    transfer_to_account_u512::delegate();
}

fn store() -> ContractHash {
    let mut entry_points = {
        let mut entry_points = EntryPoints::new();

        let entry_point = EntryPoint::new(
            FUNCTION_NAME,
            vec![
                Parameter::new(ARG_TARGET, PublicKey::cl_type()),
                Parameter::new(ARG_AMOUNT, CLType::U512),
            ],
            CLType::Unit,
            EntryPointAccess::Public,
            EntryPointType::Contract,
        );

        entry_points.add_entry_point(entry_point);

        entry_points
    };
    storage::new_contract(entry_points, None, None, None)
}

#[no_mangle]
pub extern "C" fn call() {
    let contract_hash = store();
    runtime::put_key(CONTRACT_NAME, contract_hash.into());
}
