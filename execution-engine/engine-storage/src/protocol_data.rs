use engine_wasm_prep::wasm_costs::{WasmCosts, WASM_COSTS_SERIALIZED_LENGTH};
use std::collections::BTreeMap;
use types::{
    bytesrepr::{self, FromBytes, ToBytes},
    ContractHash, HashAddr, KEY_HASH_LENGTH,
};

const PROTOCOL_DATA_SERIALIZED_LENGTH: usize = WASM_COSTS_SERIALIZED_LENGTH + 3 * KEY_HASH_LENGTH;
const DEFAULT_ADDRESS: [u8; 32] = [0; 32];

/// Represents a protocol's data. Intended to be associated with a given protocol version.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct ProtocolData {
    wasm_costs: WasmCosts,
    mint: ContractHash,
    proof_of_stake: ContractHash,
    standard_payment: ContractHash,
}

/// Provides a default instance with non existing urefs and empty costs table.
///
/// Used in contexts where PoS or Mint contract is not ready yet, and pos, and
/// mint installers are ran. For use with caution.
impl Default for ProtocolData {
    fn default() -> ProtocolData {
        ProtocolData {
            wasm_costs: WasmCosts::default(),
            mint: DEFAULT_ADDRESS,
            proof_of_stake: DEFAULT_ADDRESS,
            standard_payment: DEFAULT_ADDRESS,
        }
    }
}

impl ProtocolData {
    /// Creates a new [`ProtocolData`] value from a given [`WasmCosts`] value.
    pub fn new(
        wasm_costs: WasmCosts,
        mint: ContractHash,
        proof_of_stake: ContractHash,
        standard_payment: ContractHash,
    ) -> Self {
        ProtocolData {
            wasm_costs,
            mint,
            proof_of_stake,
            standard_payment,
        }
    }

    /// Creates a new, partially-valid [`ProtocolData`] value where only the mint URef is known.
    ///
    /// Used during `commit_genesis` before all system contracts' URefs are known.
    pub fn partial_with_mint(mint: ContractHash) -> Self {
        ProtocolData {
            mint,
            ..Default::default()
        }
    }

    /// Creates a new, partially-valid [`ProtocolData`] value where all but the standard payment
    /// uref is known.
    ///
    /// Used during `commit_genesis` before all system contracts' URefs are known.
    pub fn partial_without_standard_payment(
        wasm_costs: WasmCosts,
        mint: ContractHash,
        proof_of_stake: ContractHash,
    ) -> Self {
        ProtocolData {
            wasm_costs,
            mint,
            proof_of_stake,
            ..Default::default()
        }
    }

    /// Gets the [`WasmCosts`] value from a given [`ProtocolData`] value.
    pub fn wasm_costs(&self) -> &WasmCosts {
        &self.wasm_costs
    }

    pub fn mint(&self) -> ContractHash {
        self.mint
    }

    pub fn proof_of_stake(&self) -> ContractHash {
        self.proof_of_stake
    }

    pub fn standard_payment(&self) -> ContractHash {
        self.standard_payment
    }

    /// Retrieves all valid system contracts stored in protocol version
    pub fn system_contracts(&self) -> Vec<ContractHash> {
        let mut vec = Vec::with_capacity(3);
        if self.mint != DEFAULT_ADDRESS {
            vec.push(self.mint)
        }
        if self.proof_of_stake != DEFAULT_ADDRESS {
            vec.push(self.proof_of_stake)
        }
        if self.standard_payment != DEFAULT_ADDRESS {
            vec.push(self.standard_payment)
        }
        vec
    }

    pub fn update_from(&mut self, updates: BTreeMap<ContractHash, ContractHash>) -> bool {
        for (old_hash, new_hash) in updates {
            if old_hash == self.mint {
                self.mint = new_hash;
            } else if old_hash == self.proof_of_stake {
                self.proof_of_stake = new_hash;
            } else if old_hash == self.standard_payment {
                self.standard_payment = new_hash;
            } else {
                return false;
            }
        }
        true
    }
}

impl ToBytes for ProtocolData {
    fn to_bytes(&self) -> Result<Vec<u8>, bytesrepr::Error> {
        let mut ret = bytesrepr::unchecked_allocate_buffer(self);
        ret.append(&mut self.wasm_costs.to_bytes()?);
        ret.append(&mut self.mint.to_bytes()?);
        ret.append(&mut self.proof_of_stake.to_bytes()?);
        ret.append(&mut self.standard_payment.to_bytes()?);
        Ok(ret)
    }

    fn serialized_length(&self) -> usize {
        PROTOCOL_DATA_SERIALIZED_LENGTH
    }
}

impl FromBytes for ProtocolData {
    fn from_bytes(bytes: &[u8]) -> Result<(Self, &[u8]), bytesrepr::Error> {
        let (wasm_costs, rem) = WasmCosts::from_bytes(bytes)?;
        let (mint, rem) = HashAddr::from_bytes(rem)?;
        let (proof_of_stake, rem) = HashAddr::from_bytes(rem)?;
        let (standard_payment, rem) = HashAddr::from_bytes(rem)?;

        Ok((
            ProtocolData {
                wasm_costs,
                mint,
                proof_of_stake,
                standard_payment,
            },
            rem,
        ))
    }
}

#[cfg(test)]
pub(crate) mod gens {
    use proptest::prop_compose;

    use engine_wasm_prep::wasm_costs::gens as wasm_costs_gens;
    use types::gens;

    use super::ProtocolData;

    prop_compose! {
        pub fn protocol_data_arb()(
            wasm_costs in wasm_costs_gens::wasm_costs_arb(),
            mint in gens::u8_slice_32(),
            proof_of_stake in gens::u8_slice_32(),
            standard_payment in gens::u8_slice_32(),
        ) -> ProtocolData {
            ProtocolData {
                wasm_costs,
                mint,
                proof_of_stake,
                standard_payment,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use proptest::proptest;

    use engine_wasm_prep::wasm_costs::WasmCosts;
    use types::{bytesrepr, ContractHash};

    use super::{gens, ProtocolData};

    fn wasm_costs_mock() -> WasmCosts {
        WasmCosts {
            regular: 1,
            div: 16,
            mul: 4,
            mem: 2,
            initial_mem: 4096,
            grow_mem: 8192,
            memcpy: 1,
            max_stack_height: 64 * 1024,
            opcodes_mul: 3,
            opcodes_div: 8,
        }
    }

    fn wasm_costs_free() -> WasmCosts {
        WasmCosts {
            regular: 0,
            div: 0,
            mul: 0,
            mem: 0,
            initial_mem: 4096,
            grow_mem: 8192,
            memcpy: 0,
            max_stack_height: 64 * 1024,
            opcodes_mul: 1,
            opcodes_div: 1,
        }
    }

    #[test]
    fn should_serialize_and_deserialize() {
        let mock = {
            let costs = wasm_costs_mock();
            let mint_reference = [1u8; 32];
            let proof_of_stake_reference = [2u8; 32];
            let standard_payment_reference = [3u8; 32];
            ProtocolData::new(
                costs,
                mint_reference,
                proof_of_stake_reference,
                standard_payment_reference,
            )
        };
        let free = {
            let costs = wasm_costs_free();
            let mint_reference = [0u8; 32];
            let proof_of_stake_reference = [1u8; 32];
            let standard_payment_reference = [2u8; 32];
            ProtocolData::new(
                costs,
                mint_reference,
                proof_of_stake_reference,
                standard_payment_reference,
            )
        };
        bytesrepr::test_serialization_roundtrip(&mock);
        bytesrepr::test_serialization_roundtrip(&free);
    }

    #[test]
    fn should_return_all_system_contracts() {
        let mint_reference = [1u8; 32];
        let proof_of_stake_reference = [2u8; 32];
        let standard_payment_reference = [3u8; 32];
        let protocol_data = {
            let costs = wasm_costs_mock();
            ProtocolData::new(
                costs,
                mint_reference,
                proof_of_stake_reference,
                standard_payment_reference,
            )
        };

        let actual = {
            let mut items = protocol_data.system_contracts();
            items.sort();
            items
        };

        assert_eq!(actual.len(), 3);
        assert_eq!(actual[0], mint_reference);
        assert_eq!(actual[1], proof_of_stake_reference);
        assert_eq!(actual[2], standard_payment_reference);
    }

    #[test]
    fn should_return_only_valid_system_contracts() {
        let expected: Vec<ContractHash> = vec![];
        assert_eq!(ProtocolData::default().system_contracts(), expected);

        let mint_reference = [0u8; 32]; // <-- invalid addr
        let proof_of_stake_reference = [2u8; 32];
        let standard_payment_reference = [3u8; 32];
        let protocol_data = {
            let costs = wasm_costs_mock();
            ProtocolData::new(
                costs,
                mint_reference,
                proof_of_stake_reference,
                standard_payment_reference,
            )
        };

        let actual = {
            let mut items = protocol_data.system_contracts();
            items.sort();
            items
        };

        assert_eq!(actual.len(), 2);
        assert_eq!(actual[0], proof_of_stake_reference);
        assert_eq!(actual[1], standard_payment_reference);
    }

    proptest! {
        #[test]
        fn should_serialize_and_deserialize_with_arbitrary_values(
            protocol_data in gens::protocol_data_arb()
        ) {
            bytesrepr::test_serialization_roundtrip(&protocol_data);
        }
    }
}
