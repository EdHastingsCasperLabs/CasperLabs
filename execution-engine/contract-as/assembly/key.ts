import * as externals from "./externals";
import {readHostBuffer} from ".";
import {KEY_UREF_SERIALIZED_LENGTH} from "./constants";
import {URef} from "./uref";
import {CLValue} from "./clvalue";
import {Error, ErrorCode} from "./error";
import {checkTypedArrayEqual, typedToArray} from "./utils";
import {Result, Ref, Error as BytesreprError} from "./bytesrepr";

/**
 * Enum representing a variant of a [[Key]] - Account, Hash or URef.
 */
export enum KeyVariant {
    /** The Account variant */
    ACCOUNT_ID = 0,
    /** The Hash variant */
    HASH_ID = 1,
    /** The URef variant */
    UREF_ID = 2,
}

/**
 * The ID of an ED25519 public key.
 */
export const PUBLIC_KEY_ED25519_ID: u8 = 0;

/** A cryptographic public key. */
export class PublicKey {
    /**
     * Constructs a new `PublicKey`.
     *
     * @param variant An ID of the used key variant.
     * @param bytes The bytes constituting the public key.
     */
    constructor(public variant: u8, public bytes: Uint8Array) {}

    /** Checks whether two `PublicKey`s are equal. */
    @operator("==")
    equalsTo(other: PublicKey): bool {
        return this.variant == other.variant && checkTypedArrayEqual(this.bytes, other.bytes);
    }

    /** Checks whether two `PublicKey`s are not equal. */
    @operator("!=")
    notEqualsTo(other: PublicKey): bool {
        return !this.equalsTo(other);
    }

    /** Deserializes a `PublicKey` from an array of bytes. */
    static fromBytes(bytes: Uint8Array): Result<PublicKey> {
        if (bytes.length < 32) {
            return new Result<PublicKey>(null, BytesreprError.EarlyEndOfStream, 0);
        }

        let publicKeyBytes = bytes.subarray(0, 32);
        let publicKey = new PublicKey(PUBLIC_KEY_ED25519_ID, publicKeyBytes);
        let ref = new Ref<PublicKey>(publicKey);
        return new Result<PublicKey>(ref, BytesreprError.Ok, 32);
    }

    /** Serializes a `PublicKey` into an array of bytes. */
    toBytes(): Array<u8> {
        return typedToArray(this.bytes);
    }
}

/**
 * The type under which data (e.g. [[CLValue]]s, smart contracts, user accounts)
 * are indexed on the network.
 */
export class Key {
    variant: KeyVariant;
    hash: Uint8Array | null;
    uref: URef | null;
    account: PublicKey | null;

    /** Creates a `Key` from a given [[URef]]. */
    static fromURef(uref: URef): Key {
        let key = new Key();
        key.variant = KeyVariant.UREF_ID;
        key.uref = uref;
        return key;
    }

    /** Creates a `Key` from a given hash. */
    static fromHash(hash: Uint8Array): Key {
        let key = new Key();
        key.variant = KeyVariant.HASH_ID;
        key.hash = hash;
        return key;
    }

    /** Creates a `Key` from a [[PublicKey]] representing an account. */
    static fromAccount(account: PublicKey): Key {
        let key = new Key();
        key.variant = KeyVariant.ACCOUNT_ID;
        key.account = account;
        return key;
    }

    /**
     * Attempts to write `value` under a new Key::URef
     *
     * If a key is returned it is always of [[KeyVariant]].UREF_ID
     */
    static create(value: CLValue): Key | null {
        const valueBytes = value.toBytes();
        let keyBytes = new Uint8Array(KEY_UREF_SERIALIZED_LENGTH);
        externals.new_uref(
            keyBytes.dataStart,
            valueBytes.dataStart,
            valueBytes.length
        );
        const keyResult = Key.fromBytes(keyBytes);
        if (keyResult.hasError()) {
            return null;
        }
        let key = keyResult.value;
        if (key.variant != KeyVariant.UREF_ID) {
            return null;
        }
        return key;
    }

    /** Deserializes a `Key` from an array of bytes. */
    static fromBytes(bytes: Uint8Array): Result<Key> {
        if (bytes.length < 1) {
            return new Result<Key>(null, BytesreprError.EarlyEndOfStream, 0);
        }
        const tag = bytes[0];
        let currentPos = 1;

        if (tag == KeyVariant.HASH_ID) {
            var hashBytes = bytes.subarray(1, 32 + 1);
            currentPos += 32;

            let key = Key.fromHash(hashBytes);
            let ref = new Ref<Key>(key);
            return new Result<Key>(ref, BytesreprError.Ok, currentPos);
        }
        else if (tag == KeyVariant.UREF_ID) {
            var urefBytes = bytes.subarray(1);
            var urefResult = URef.fromBytes(urefBytes);
            if (urefResult.error != BytesreprError.Ok) {
                return new Result<Key>(null, urefResult.error, 0);
            }
            let key = Key.fromURef(urefResult.value);
            let ref = new Ref<Key>(key);
            return new Result<Key>(ref, BytesreprError.Ok, currentPos + urefResult.position);
        }
        else if (tag == KeyVariant.ACCOUNT_ID) {
            let publicKeyBytes = bytes.subarray(1);
            let publicKeyResult = PublicKey.fromBytes(publicKeyBytes);
            if (publicKeyResult.hasError()) {
                return new Result<Key>(null, publicKeyResult.error, currentPos);
            }
            currentPos += publicKeyResult.position;
            let key = Key.fromAccount(publicKeyResult.value);
            let ref = new Ref<Key>(key);
            return new Result<Key>(ref, BytesreprError.Ok, currentPos);
        }
        else {
            return new Result<Key>(null, BytesreprError.FormattingError, currentPos);
        }
    }

    /** Serializes a `Key` into an array of bytes. */
    toBytes(): Array<u8> {
        if(this.variant == KeyVariant.UREF_ID){
            let bytes = new Array<u8>();
            bytes.push(<u8>this.variant)
            bytes = bytes.concat((<URef>this.uref).toBytes());
            return bytes;
        }
        else if (this.variant == KeyVariant.HASH_ID) {
            var hashBytes = <Uint8Array>this.hash;
            let bytes = new Array<u8>(1 + hashBytes.length);
            bytes[0] = <u8>this.variant;
            for (let i = 0; i < hashBytes.length; i++) {
                bytes[i + 1] = hashBytes[i];
            }
            return bytes;
        }
        else if (this.variant == KeyVariant.ACCOUNT_ID) {
            let bytes = new Array<u8>();
            bytes.push(<u8>this.variant);
            bytes = bytes.concat((<PublicKey>this.account).toBytes());
            return bytes;
        }
        else {
            return <Array<u8>>unreachable();
        }
    }

    /** Checks whether the `Key` is of [[KeyVariant]].UREF_ID. */
    isURef(): bool {
        return this.variant == KeyVariant.UREF_ID;
    }

    /** Converts the `Key` into `URef`. */
    toURef(): URef {
        return <URef>this.uref;
    }

    /** Reads the data stored under this `Key`. */
    read(): Uint8Array | null {
        const keyBytes = this.toBytes();
        let valueSize = new Uint8Array(1);
        const ret = externals.read_value(keyBytes.dataStart, keyBytes.length, valueSize.dataStart);
        const error = Error.fromResult(ret);
        if (error != null) {
            if (error.value() == ErrorCode.ValueNotFound) {
                return null;
            }
            error.revert();
            return <Uint8Array>unreachable();
        }
        // TODO: How can we have `read<T>` that would deserialize host bytes into T?
        return readHostBuffer(valueSize[0]);
    }

    /** Stores a [[CLValue]] under this `Key`. */
    write(value: CLValue): void {
        const keyBytes = this.toBytes();
        const valueBytes = value.toBytes();
        externals.write(
            keyBytes.dataStart,
            keyBytes.length,
            valueBytes.dataStart,
            valueBytes.length
        );
    }

    /** Adds the given `CLValue` to a value already stored under this `Key`. */
    add(value: CLValue): void {
        const keyBytes = this.toBytes();
        const valueBytes = value.toBytes();

        externals.add(
            keyBytes.dataStart,
            keyBytes.length,
            valueBytes.dataStart,
            valueBytes.length
        );
    }

    /** Checks whether two `Key`s are equal. */
    @operator("==")
    equalsTo(other: Key): bool {
        if (this.variant == KeyVariant.UREF_ID) {
            if (other.variant == KeyVariant.UREF_ID) {
                return <URef>this.uref == <URef>other.uref;
            }
            else {
                return false;
            }
        }
        else if (this.variant == KeyVariant.HASH_ID) {
            if (other.variant == KeyVariant.HASH_ID) {
                return checkTypedArrayEqual(<Uint8Array>this.hash, <Uint8Array>other.hash);

            }
            else {
                return false;
            }
        }
        else if (this.variant == KeyVariant.ACCOUNT_ID) {
            if (other.variant == KeyVariant.ACCOUNT_ID) {
                return <PublicKey>this.account == <PublicKey>other.account;
            }
            else {
                return false;
            }
        }
        else {
            return false;
        }
    }

    /** Checks whether two keys are not equal. */
    @operator("!=")
    notEqualsTo(other: Key): bool {
        return !this.equalsTo(other);
    }
}
