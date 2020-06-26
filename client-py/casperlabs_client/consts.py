DEFAULT_HOST = "localhost"
DEFAULT_PORT = 40401
DEFAULT_INTERNAL_PORT = 40402
STATUS_CHECK_DELAY = 0.5
STATUS_TIMEOUT = 180  # 3 minutes
DEFAULT_PAYMENT_AMOUNT = 10000000
VISUALIZE_DAG_STREAM_DELAY = 5

ED25519_KEY_ALGORITHM = "ed25519"
SECP256K1_KEY_ALGORITHM = "secp256k1"
# To be used in ECO-463 with SECR256K1_SECURE_ENCLAVE_KEY_ALGORITHM = "secr256k1"
SUPPORTED_KEY_ALGORITHMS = (ED25519_KEY_ALGORITHM, SECP256K1_KEY_ALGORITHM)

DEFAULT_KEY_FILENAME_PREFIX: str = "account"
VALIDATOR_KEY_FILENAME_PREFIX: str = "validator"
ACCOUNT_PRIVATE_KEY_FILENAME_SUFFIX: str = "-private.pem"
ACCOUNT_PUBLIC_KEY_FILENAME_SUFFIX: str = "-public.pem"
ACCOUNT_HASH_FILENAME_SUFFIX: str = "-id-hex"

ACCOUNT_HASH_LENGTH: int = 32

VALIDATOR_PRIVATE_KEY_FILENAME = "validator-private.pem"
VALIDATOR_PUBLIC_KEY_FILENAME = "validator-public.pem"
VALIDATOR_ID_FILENAME = "validator-id"
VALIDATOR_ID_HEX_FILENAME = "validator-id-hex"
NODE_PRIVATE_KEY_FILENAME = "node.key.pem"
NODE_CERTIFICATE_FILENAME = "node.certificate.pem"
NODE_ID_FILENAME = "node-id"
