#!/usr/bin/env python3
"""
CasperLabs Client API library and command line tool.
"""

# Hack to fix the relative imports problems #
import sys
from pathlib import Path

file = Path(__file__).resolve()
parent, root = file.parent, file.parents[1]
sys.path.append(str(root))

# end of hack #
import os
import time
import argparse
import grpc
from grpc._channel import _Rendezvous
import ssl
import functools
from pyblake2 import blake2b
import ed25519
import base64
import json
import struct
import logging
import pkg_resources

# Monkey patching of google.protobuf.text_encoding.CEscape
# to get keys and signatures in hex when printed
import google.protobuf.text_format

CEscape = google.protobuf.text_format.text_encoding.CEscape

base64_b64decode = base64.b64decode


def _hex(text, as_utf8):
    try:
        return (len(text) in (32, 64, 20)) and text.hex() or CEscape(text, as_utf8)
    except TypeError:
        return CEscape(text, as_utf8)


google.protobuf.text_format.text_encoding.CEscape = _hex

# ~/CasperLabs/protobuf/io/casperlabs/node/api/control.proto
from .control_pb2_grpc import ControlServiceStub
from . import control_pb2 as control

# ~/CasperLabs/protobuf/io/casperlabs/node/api/casper.proto
from . import casper_pb2 as casper
from .casper_pb2_grpc import CasperServiceStub

# ~/CasperLabs/protobuf/io/casperlabs/casper/consensus/consensus.proto
from . import consensus_pb2 as consensus, state_pb2 as state

# ~/CasperLabs/protobuf/io/casperlabs/casper/consensus/info.proto
from . import info_pb2 as info

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 40401
DEFAULT_INTERNAL_PORT = 40402


from google.protobuf import json_format

Arg = consensus.Deploy.Arg
Value = consensus.Deploy.Arg.Value


class ABI:
    """
    Serialize deploy arguments.
    """

    @staticmethod
    def optional_value(name, a):
        if a is None:
            return Arg(name=name, value=Value(optional_value=Value()))
        return Arg(name=name, value=Value(optional_value=a.value))

    @staticmethod
    def bytes_value(name, a: bytes):
        return Arg(name=name, value=Value(bytes_value=a))

    @staticmethod
    def account(name, a):
        if type(a) == bytes and len(a) == 32:
            return ABI.byte_array(name, a)
        if type(a) == str and len(a) == 64:
            return ABI.byte_array(name, bytes.fromhex(a))
        raise Exception("account must be 32 bytes or 64 characters long string")

    @staticmethod
    def int_value(name, a: int):
        return Arg(name=name, value=Value(int_value=a))

    @staticmethod
    def long_value(name, a: int):
        return Arg(name=name, value=Value(long_value=a))

    @staticmethod
    def big_int(name, a):
        return Arg(
            name=name, value=Value(big_int=state.BigInt(value=str(a), bit_width=512))
        )

    @staticmethod
    def string_value(name, a):
        return Arg(name=name, value=Value(string_value=a))

    @staticmethod
    def args(l: list):
        c = consensus.Deploy.Code(args=l)
        return c.args

    @staticmethod
    def args_from_json(s):
        base64_b64decode = base64.b64decode
        try:
            # Change JSON protobuf format of binary data from base64 to base16
            base64.b64decode = lambda s: bytes.fromhex(s)
            parsed_json = json.loads(s)
            args = [
                json_format.ParseDict(d, consensus.Deploy.Arg()) for d in parsed_json
            ]
            c = consensus.Deploy.Code(args=args)
            return c.args
        finally:
            base64.b64decode = base64_b64decode

    @staticmethod
    def args_to_json(args):
        base64_b64encode = base64.b64encode
        try:
            # We can't just call MessageToDict or MessageToJson on the args object,
            # which is a 'repeated Arg', because we get:
            # AttributeError: 'google.protobuf.pyext._message.RepeatedCompositeCo' object has no attribute 'DESCRIPTOR'
            class Mock:
                def __init__(self, v):
                    self.value = v

                def decode(self, s):
                    return self.value

            base64.b64encode = lambda b: Mock(b.hex())
            return json.dumps(
                [
                    json_format.MessageToDict(arg, preserving_proto_field_name=True)
                    for arg in args
                ]
            )
        finally:
            base64.b64encode = base64_b64encode

    # Below methods for backwards compatibility

    @staticmethod
    def u32(name, n: int):
        return ABI.int_value(name, n)

    @staticmethod
    def u64(name, n: int):
        return ABI.long_value(name, n)

    @staticmethod
    def u512(name, n: int):
        return ABI.big_int(name, n)

    @staticmethod
    def byte_array(name, a):
        return Arg(name=name, value=Value(bytes_value=a))


def read_pem_key(file_name: str):
    with open(file_name) as f:
        s = [l for l in f.readlines() if l and not l.startswith("-----")][0].strip()
        r = base64_b64decode(s)
        return len(r) % 32 == 0 and r[:32] or r[-32:]


class InternalError(Exception):
    """
    The only exception that API calls can throw.
    Internal errors like gRPC exceptions will be caught
    and this exception thrown instead, so the user does
    not have to worry about handling any other exceptions.
    """

    def __init__(self, status="", details=""):
        super(InternalError, self).__init__()
        self.status = status
        self.details = details

    def __str__(self):
        return f"{self.status}: {self.details}"


def api(function):
    """
    Decorator of API functions that protects user code from
    unknown exceptions raised by gRPC or internal API errors.
    It will catch all exceptions and throw InternalError.

    :param function: function to be decorated
    :return:
    """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (SyntaxError, TypeError, InternalError):
            raise
        except _Rendezvous as e:
            raise InternalError(str(e.code()), e.details())
        except Exception as e:
            raise InternalError(details=str(e)) from e

    return wrapper


def blake2b_hash(data: bytes) -> bytes:
    h = blake2b(digest_size=32)
    h.update(data)
    return h.digest()


def _read_binary(file_name: str):
    with open(file_name, "rb") as f:
        return f.read()


def _encode_contract(contract_options, contract_args):
    """
    """
    file_name, hash, name, uref = contract_options
    C = consensus.Deploy.Code
    if file_name:
        return C(wasm=_read_binary(file_name), args=contract_args)
    if hash:
        return C(hash=hash, args=contract_args)
    if name:
        return C(name=name, args=contract_args)
    if uref:
        return C(uref=uref, args=contract_args)
    raise Exception("One of wasm, hash, name or uref is required")


def signature(private_key, data: bytes):
    return private_key and consensus.Signature(
        sig_algorithm="ed25519",
        sig=ed25519.SigningKey(read_pem_key(private_key)).sign(data),
    )


def _serialize(o) -> bytes:
    return o.SerializeToString()


NUMBER_OF_RETRIES = 5

# Initial delay in seconds before an attempt to retry
INITIAL_DELAY = 0.3


def retry_wrapper(function, *args):
    delay = INITIAL_DELAY
    for i in range(NUMBER_OF_RETRIES):
        try:
            return function(*args)
        except _Rendezvous as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE and i < NUMBER_OF_RETRIES - 1:
                logging.warning(f"Retrying after {e} in {delay} seconds")
                time.sleep(delay)
                delay += delay
            else:
                raise


def retry_unary(function):
    @functools.wraps(function)
    def wrapper(*args):
        return retry_wrapper(function, *args)

    return wrapper


def retry_stream(function):
    @functools.wraps(function)
    def wrapper(*args):
        yield from retry_wrapper(function, *args)

    return wrapper


class InsecureGRPCService:
    def __init__(self, host, port, serviceStub):
        self.address = f"{host}:{port}"
        self.serviceStub = serviceStub

    def __getattr__(self, name):

        logging.warning(
            f"Creating insecure connection to {self.address} ({self.serviceStub})"
        )

        @retry_unary
        def unary_unary(*args):
            logging.debug(
                f"Insecure {self.address} ({self.serviceStub}): {name} {list(args)}"
            )
            with grpc.insecure_channel(self.address) as channel:
                return getattr(self.serviceStub(channel), name)(*args)

        @retry_stream
        def unary_stream(*args):
            logging.debug(
                f"Insecure {self.address} ({self.serviceStub}): {name} {list(args)}"
            )
            with grpc.insecure_channel(self.address) as channel:
                yield from getattr(self.serviceStub(channel), name[: -len("_stream")])(
                    *args
                )

        return name.endswith("_stream") and unary_stream or unary_unary


def extract_common_name(certificate_file: str) -> str:
    cert_dict = ssl._ssl._test_decode_cert(certificate_file)
    return [t[0][1] for t in cert_dict["subject"] if t[0][0] == "commonName"][0]


class SecureGRPCService:
    def __init__(self, host, port, serviceStub, node_id, certificate_file):
        self.address = f"{host}:{port}"
        self.serviceStub = serviceStub
        self.node_id = node_id or extract_common_name(certificate_file)
        self.certificate_file = certificate_file
        with open(self.certificate_file, "rb") as f:
            self.credentials = grpc.ssl_channel_credentials(f.read())
        self.secure_channel_options = self.node_id and (
            ("grpc.ssl_target_name_override", self.node_id),
            ("grpc.default_authority", self.node_id),
        )

    def __getattr__(self, name):
        logging.debug(
            f"Creating secure connection to {self.address} ({self.serviceStub})"
        )

        @retry_unary
        def unary_unary(*args):
            with grpc.secure_channel(
                self.address, self.credentials, options=self.secure_channel_options
            ) as channel:
                return getattr(self.serviceStub(channel), name)(*args)

        @retry_stream
        def unary_stream(*args):
            with grpc.secure_channel(
                self.address, self.credentials, options=self.secure_channel_options
            ) as channel:
                yield from getattr(self.serviceStub(channel), name[: -len("_stream")])(
                    *args
                )

        return name.endswith("_stream") and unary_stream or unary_unary


class CasperLabsClient:
    """
    gRPC CasperLabs client.
    """

    # Note, there is also casper.StateQuery.KeyVariant.KEY_VARIANT_UNSPECIFIED,
    # but it doesn't seem to have an official string representation
    # ("key_variant_unspecified"? "unspecified"?) and is not used by the client.
    STATE_QUERY_KEY_VARIANT = {
        "hash": casper.StateQuery.KeyVariant.HASH,
        "uref": casper.StateQuery.KeyVariant.UREF,
        "address": casper.StateQuery.KeyVariant.ADDRESS,
        "local": casper.StateQuery.KeyVariant.LOCAL,
    }

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        port_internal: int = DEFAULT_INTERNAL_PORT,
        node_id: str = None,
        certificate_file: str = None,
    ):
        """
        CasperLabs client's constructor.

        :param host:            Hostname or IP of node on which gRPC service is running
        :param port:            Port used for external gRPC API
        :param port_internal:   Port used for internal gRPC API
        :param certificate_file:      Certificate file for TLS
        :param node_id:         node_id of the node, for gRPC encryption
        """
        self.host = host
        self.port = port
        self.port_internal = port_internal
        self.node_id = node_id
        self.certificate_file = certificate_file

        if node_id:
            self.casperService = SecureGRPCService(
                host, port, CasperServiceStub, node_id, certificate_file
            )
            self.controlService = SecureGRPCService(
                # We currently assume that if node_id is given then
                # we get certificate_file too. This is unlike in the Scala client
                # where node_id is all that's needed for configuring secure connection.
                # The reason for this is that currently it doesn't seem to be possible
                # to open a secure grpc connection in Python without supplying any
                # certificate on the client side.
                host,
                port_internal,
                ControlServiceStub,
                node_id,
                certificate_file,
            )
        else:
            self.casperService = InsecureGRPCService(host, port, CasperServiceStub)
            self.controlService = InsecureGRPCService(
                host, port_internal, ControlServiceStub
            )

    @api
    def make_deploy(
        self,
        from_addr: bytes = None,
        gas_price: int = 10,
        payment: str = None,
        session: str = None,
        public_key: str = None,
        private_key: str = None,
        session_args: bytes = None,
        payment_args: bytes = None,
        payment_hash: bytes = None,
        payment_name: str = None,
        payment_uref: bytes = None,
        session_hash: bytes = None,
        session_name: str = None,
        session_uref: bytes = None,
        ttl_millis: int = 0,
    ):
        """
        Create a deploy message. See deploy documentation.
        """
        # Convert from hex to binary.
        if from_addr and len(from_addr) == 64:
            from_addr = bytes.fromhex(from_addr)

        if from_addr and len(from_addr) != 32:
            raise Exception(f"from_addr must be 32 bytes")

        session_options = (session, session_hash, session_name, session_uref)
        payment_options = (payment, payment_hash, payment_name, payment_uref)

        # Compatibility mode, should be removed when payment is obligatory
        if len(list(filter(None, payment_options))) == 0:
            logging.info("No payment contract provided, using session as payment")
            payment_options = session_options

        if len(list(filter(None, session_options))) != 1:
            raise TypeError(
                "deploy: only one of session, session_hash, session_name, session_uref must be provided"
            )

        if len(list(filter(None, payment_options))) != 1:
            raise TypeError(
                "deploy: only one of payment, payment_hash, payment_name, payment_uref must be provided"
            )

        # session_args must go to payment as well for now cause otherwise we'll get GASLIMIT error,
        # if payment is same as session:
        # https://github.com/CasperLabs/CasperLabs/blob/dev/casper/src/main/scala/io/casperlabs/casper/util/ProtoUtil.scala#L463
        body = consensus.Deploy.Body(
            session=_encode_contract(session_options, session_args),
            payment=_encode_contract(payment_options, payment_args),
        )

        approval_public_key = public_key and read_pem_key(public_key)
        account_public_key = from_addr or approval_public_key

        header = consensus.Deploy.Header(
            account_public_key=account_public_key,
            timestamp=int(1000 * time.time()),
            ttl_millis=ttl_millis,
            gas_price=gas_price,
            body_hash=blake2b_hash(_serialize(body)),
        )

        deploy_hash = blake2b_hash(_serialize(header))

        deploy = consensus.Deploy(deploy_hash=deploy_hash, header=header, body=body)
        return self.sign_deploy(deploy, approval_public_key, private_key)

    @api
    def sign_deploy(self, deploy, public_key, private_key):
        deploy.approvals.extend(
            [
                consensus.Approval(
                    approver_public_key=public_key,
                    signature=signature(private_key, deploy.deploy_hash),
                )
            ]
        )
        return deploy

    @api
    def deploy(
        self,
        from_addr: bytes = None,
        gas_price: int = 10,
        payment: str = None,
        session: str = None,
        public_key: str = None,
        private_key: str = None,
        session_args: bytes = None,
        payment_args: bytes = None,
        payment_hash: bytes = None,
        payment_name: str = None,
        payment_uref: bytes = None,
        session_hash: bytes = None,
        session_name: str = None,
        session_uref: bytes = None,
        ttl_millis: int = 0,
    ):
        """
        Deploy a smart contract source file to Casper on an existing running node.
        The deploy will be packaged and sent as a block to the network depending
        on the configuration of the Casper instance.

        :param from_addr:     Purse address that will be used to pay for the deployment.
        :param gas_price:     The price of gas for this transaction in units dust/gas.
                              Must be positive integer.
        :param payment:       Path to the file with payment code.
        :param session:       Path to the file with session code.
        :param public_key:    Path to a file with public key (Ed25519)
        :param private_key:   Path to a file with private key (Ed25519)
        :param session_args:  List of ABI encoded arguments of session contract
        :param payment_args:  List of ABI encoded arguments of payment contract
        :param session-hash:  Hash of the stored contract to be called in the
                              session; base16 encoded.
        :param session-name:  Name of the stored contract (associated with the
                              executing account) to be called in the session.
        :param session-uref:  URef of the stored contract to be called in the
                              session; base16 encoded.
        :param payment-hash:  Hash of the stored contract to be called in the
                              payment; base16 encoded.
        :param payment-name:  Name of the stored contract (associated with the
                              executing account) to be called in the payment.
        :param payment-uref:  URef of the stored contract to be called in the
                              payment; base16 encoded.
        :ttl_millis:          Time to live. Time (in milliseconds) that the
                              deploy will remain valid for.
        :return:              Tuple: (deserialized DeployServiceResponse object, deploy_hash)
        """

        deploy = self.make_deploy(
            from_addr=from_addr,
            gas_price=gas_price,
            payment=payment,
            session=session,
            public_key=public_key,
            private_key=private_key,
            session_args=session_args,
            payment_args=payment_args,
            payment_hash=payment_hash,
            payment_name=payment_name,
            payment_uref=payment_uref,
            session_hash=session_hash,
            session_name=session_name,
            session_uref=session_uref,
            ttl_millis=ttl_millis,
        )

        # TODO: Return only deploy_hash
        return self.send_deploy(deploy), deploy.deploy_hash

    @api
    def send_deploy(self, deploy):
        # TODO: Deploy returns Empty, error handing via exceptions, apparently,
        # so no point in returning it.
        return self.casperService.Deploy(casper.DeployRequest(deploy=deploy))

    @api
    def showBlocks(self, depth: int = 1, max_rank=0, full_view=True):
        """
        Get slices of the DAG, going backwards, rank by rank.

        :param depth:     How many of the top ranks of the DAG to show.
        :param max_rank:  Maximum rank to go back from.
                          0 means go from the current tip of the DAG.
        :param full_view: Full view if True, otherwise basic.
        :return:          Generator of block info objects.
        """
        yield from self.casperService.StreamBlockInfos_stream(
            casper.StreamBlockInfosRequest(
                depth=depth,
                max_rank=max_rank,
                view=(
                    full_view and info.BlockInfo.View.FULL or info.BlockInfo.View.BASIC
                ),
            )
        )

    @api
    def showBlock(self, block_hash_base16: str, full_view=True):
        """
        Returns object describing a block known by Casper on an existing running node.

        :param block_hash_base16: hash of the block to be retrieved
        :param full_view:         full view if True, otherwise basic
        :return:                  object representing the retrieved block
        """
        return self.casperService.GetBlockInfo(
            casper.GetBlockInfoRequest(
                block_hash_base16=block_hash_base16,
                view=(
                    full_view and info.BlockInfo.View.FULL or info.BlockInfo.View.BASIC
                ),
            )
        )

    @api
    def propose(self):
        """"
        Propose a block using deploys in the pool.

        :return:    response object with block_hash
        """
        return self.controlService.Propose(control.ProposeRequest())

    @api
    def visualizeDag(
        self,
        depth: int,
        out: str = None,
        show_justification_lines: bool = False,
        stream: str = None,
    ):
        """
        Retrieve DAG in DOT format.

        :param depth:                     depth in terms of block height
        :param out:                       output image filename, outputs to stdout if
                                          not specified, must end with one of the png,
                                          svg, svg_standalone, xdot, plain, plain_ext,
                                          ps, ps2, json, json0
        :param show_justification_lines:  if justification lines should be shown
        :param stream:                    subscribe to changes, 'out' has to specified,
                                          valid values are 'single-output', 'multiple-outputs'
        :return:                          VisualizeBlocksResponse object
        """
        raise Exception("Not implemented yet")

    @api
    def queryState(self, blockHash: str, key: str, path: str, keyType: str):
        """
        Query a value in the global state.

        :param blockHash:         Hash of the block to query the state of
        :param key:               Base16 encoding of the base key
        :param path:              Path to the value to query. Must be of the form
                                  'key1/key2/.../keyn'
        :param keyType:           Type of base key. Must be one of 'hash', 'uref', 'address' or 'local'.
                                  For 'local' key type, 'key' value format is {seed}:{rest},
                                  where both parts are hex encoded."
        :return:                  QueryStateResponse object
        """

        def key_variant(keyType):

            variant = self.STATE_QUERY_KEY_VARIANT.get(keyType.lower(), None)
            if variant is None:
                raise InternalError(
                    "query-state", f"{keyType} is not a known query-state key type"
                )
            return variant

        q = casper.StateQuery(key_variant=key_variant(keyType), key_base16=key)
        q.path_segments.extend([name for name in path.split("/") if name])
        return self.casperService.GetBlockState(
            casper.GetBlockStateRequest(block_hash_base16=blockHash, query=q)
        )

    @api
    def balance(self, address: str, block_hash: str):
        value = self.queryState(block_hash, address, "", "address")
        account = None
        try:
            account = value.account
        except AttributeError:
            return InternalError(
                "balance", f"Expected Account type value under {address}."
            )

        urefs = [u for u in account.named_keys if u.name == "mint"]
        if len(urefs) == 0:
            raise InternalError(
                "balance",
                "Account's named_keys map did not contain Mint contract address.",
            )

        mintPublic = urefs[0]

        def abi_byte_array(a: bytes) -> bytes:
            return struct.pack("<I", len(a)) + a

        mintPublicHex = mintPublic.key.uref.uref.hex()
        purseAddrHex = abi_byte_array(account.purse_id.uref).hex()
        localKeyValue = f"{mintPublicHex}:{purseAddrHex}"

        balanceURef = self.queryState(block_hash, localKeyValue, "", "local")
        balance = self.queryState(
            block_hash, balanceURef.key.uref.uref.hex(), "", "uref"
        )
        return int(balance.big_int.value)

    @api
    def showDeploy(self, deploy_hash_base16: str, full_view=True):
        """
        Retrieve information about a single deploy by hash.
        """
        return self.casperService.GetDeployInfo(
            casper.GetDeployInfoRequest(
                deploy_hash_base16=deploy_hash_base16,
                view=(
                    full_view
                    and info.DeployInfo.View.FULL
                    or info.DeployInfo.View.BASIC
                ),
            )
        )

    @api
    def showDeploys(self, block_hash_base16: str, full_view=True):
        """
        Get the processed deploys within a block.
        """
        yield from self.casperService.StreamBlockDeploys_stream(
            casper.StreamBlockDeploysRequest(
                block_hash_base16=block_hash_base16,
                view=(
                    full_view
                    and info.DeployInfo.View.FULL
                    or info.DeployInfo.View.BASIC
                ),
            )
        )


def guarded_command(function):
    """
    Decorator of functions that implement CLI commands.

    Occasionally the node can throw some exceptions instead of properly sending us a response,
    those will be deserialized on our end and rethrown by the gRPC layer.
    In this case we want to catch the exception and return a non-zero return code to the shell.

    :param function:  function to be decorated
    :return:
    """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            rc = function(*args, **kwargs)
            # Generally the CLI commands are assumed to succeed if they don't throw,
            # but they can also return a positive error code if they need to.
            if rc is not None:
                return rc
            return 0
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1

    return wrapper


def hexify(o):
    """
    Convert protobuf message to text format with cryptographic keys and signatures in base 16.
    """
    return google.protobuf.text_format.MessageToString(o)


def _show_blocks(response, element_name="block"):
    count = 0
    for block in response:
        print(f"------------- {element_name} {count} ---------------")
        print(hexify(block))
        print("-----------------------------------------------------\n")
        count += 1
    print("count:", count)


def _show_block(response):
    print(hexify(response))


def bundled_contract(file_name):
    """
    Return path to contract file bundled with the package.
    """
    p = pkg_resources.resource_filename(__name__, file_name)
    if not os.path.exists(p):
        raise Exception(f"Missing bundled contract {file_name} ({p})")
    return p


def _set_session(args, file_name):
    """
    Use bundled contract unless one of the session* args is set.
    """
    if not any((args.session, args.session_hash, args.session_name, args.session_uref)):
        args.session = bundled_contract(file_name)


@guarded_command
def no_command(casperlabs_client, args):
    print("You must provide a command. --help for documentation of commands.")
    return 1


@guarded_command
def bond_command(casperlabs_client, args):
    logging.info(f"BOND {args}")
    _set_session(args, "bonding.wasm")

    if not args.session_args:
        args.session_args = ABI.args_to_json(
            ABI.args([ABI.long_value("amount", args.amount)])
        )

    return deploy_command(casperlabs_client, args)


@guarded_command
def unbond_command(casperlabs_client, args):
    logging.info(f"UNBOND {args}")
    _set_session(args, "unbonding.wasm")

    if not args.session_args:
        args.session_args = ABI.args_to_json(
            ABI.args(
                [ABI.optional_value("amount", ABI.long_value("amount", args.amount))]
            )
        )

    logging.info(f" XXX unbond_command: args.session_args={args.session_args}")

    return deploy_command(casperlabs_client, args)


@guarded_command
def deploy_command(casperlabs_client, args):
    from_addr = bytes.fromhex(getattr(args, "from"))
    if len(from_addr) != 32:
        raise Exception(
            "--from must be 32 bytes encoded as 64 characters long hexadecimal"
        )

    if args.payment_amount is not None:
        args.payment_args = ABI.args_to_json(
            ABI.args([ABI.big_int("amount", int(args.payment_amount))])
        )
        # Unless one of payment* options supplied use bundled standard-payment
        if not any(
            (args.payment, args.payment_name, args.payment_hash, args.payment_uref)
        ):
            p = pkg_resources.resource_filename(__name__, "standard_payment.wasm")
            if not os.path.exists(p):
                raise Exception(f"No bundled contract {p}")
            args.payment = p

    kwargs = dict(
        from_addr=from_addr,
        gas_price=args.gas_price,
        payment=args.payment or args.session,
        session=args.session,
        public_key=args.public_key or None,
        private_key=args.private_key or None,
        session_args=args.session_args
        and ABI.args_from_json(args.session_args)
        or None,
        payment_args=args.payment_args
        and ABI.args_from_json(args.payment_args)
        or None,
        payment_hash=args.payment_hash and bytes.fromhex(args.payment_hash),
        payment_name=args.payment_name,
        payment_uref=args.payment_uref and bytes.fromhex(args.payment_uref),
        session_hash=args.session_hash and bytes.fromhex(args.session_hash),
        session_name=args.session_name,
        session_uref=args.session_uref and bytes.fromhex(args.session_uref),
    )
    _, deploy_hash = casperlabs_client.deploy(**kwargs)
    print(f"Success! Deploy {deploy_hash.hex()} deployed")


@guarded_command
def propose_command(casperlabs_client, args):
    response = casperlabs_client.propose()
    print(f"Success! Block hash: {response.block_hash.hex()}")


@guarded_command
def show_block_command(casperlabs_client, args):
    response = casperlabs_client.showBlock(args.hash, full_view=True)
    return _show_block(response)


@guarded_command
def show_blocks_command(casperlabs_client, args):
    response = casperlabs_client.showBlocks(args.depth)
    _show_blocks(response)


@guarded_command
def vdag_command(casperlabs_client, args):
    response = casperlabs_client.visualizeDag(args.depth)
    # TODO: call Graphviz
    print(hexify(response))


@guarded_command
def query_state_command(casperlabs_client, args):
    response = casperlabs_client.queryState(
        args.block_hash, args.key, args.path, getattr(args, "type")
    )
    print(hexify(response))


@guarded_command
def balance_command(casperlabs_client, args):
    response = casperlabs_client.balance(args.address, args.block_hash)
    print(response)


@guarded_command
def show_deploy_command(casperlabs_client, args):
    response = casperlabs_client.showDeploy(args.hash, full_view=False)
    print(hexify(response))


@guarded_command
def show_deploys_command(casperlabs_client, args):
    response = casperlabs_client.showDeploys(args.hash, full_view=False)
    _show_blocks(response, element_name="deploy")


def main():
    """
    Parse command line and call an appropriate command.
    """

    class Parser:
        def __init__(self):
            self.parser = argparse.ArgumentParser(add_help=False)
            self.parser.add_argument(
                "--help",
                action="help",
                default=argparse.SUPPRESS,
                help="show this help message and exit",
            )
            self.parser.add_argument(
                "-h",
                "--host",
                required=False,
                default=DEFAULT_HOST,
                type=str,
                help="Hostname or IP of node on which gRPC service is running.",
            )
            self.parser.add_argument(
                "-p",
                "--port",
                required=False,
                default=DEFAULT_PORT,
                type=int,
                help="Port used for external gRPC API.",
            )
            self.parser.add_argument(
                "--port-internal",
                required=False,
                default=DEFAULT_INTERNAL_PORT,
                type=int,
                help="Port used for internal gRPC API.",
            )
            self.parser.add_argument(
                "--node-id",
                required=False,
                type=str,
                help="node_id parameter for TLS connection",
            )
            self.parser.add_argument(
                "--certificate-file",
                required=False,
                type=str,
                help="Certificate file for TLS connection",
            )
            self.sp = self.parser.add_subparsers(help="Choose a request")

            self.parser.set_defaults(function=no_command)

        def addCommand(self, command: str, function, help, arguments):
            command_parser = self.sp.add_parser(command, help=help)
            command_parser.set_defaults(function=function)
            for (args, options) in arguments:
                command_parser.add_argument(*args, **options)

        def run(self):
            if len(sys.argv) < 2:
                self.parser.print_usage()
                return 1

            args = self.parser.parse_args()
            return args.function(
                CasperLabsClient(
                    args.host,
                    args.port,
                    args.port_internal,
                    args.node_id,
                    args.certificate_file,
                ),
                args,
            )

    parser = Parser()

    # fmt: off
    deploy_options = [
        [('-f', '--from'), dict(required=True, type=str, help="The public key of the account which is the context of this deployment, base16 encoded.")],
        # TODO: handling of dependencies not implemented yet. It is not clear what the format of <arg>... is (list of args).
        [('--dependencies',), dict(required=False, type=str, help="List of deploy hashes (base16 encoded) which must be executed before this deploy.")],
        [('--payment-amount',), dict(required=False, type=int, default=None, help="Standard payment amount. Use this with the default payment, or override with --payment-args if custom payment code is used.")],
        [('--gas-price',), dict(required=False, type=int, default=10, help='The price of gas for this transaction in units dust/gas. Must be positive integer.')],
        [('-p', '--payment'), dict(required=False, type=str, default=None, help='Path to the file with payment code, by default fallbacks to the --session code')],
        [('--payment-hash',), dict(required=False, type=str, default=None, help='Hash of the stored contract to be called in the payment; base16 encoded')],
        [('--payment-name',), dict(required=False, type=str, default=None, help='Name of the stored contract (associated with the executing account) to be called in the payment')],
        [('--payment-uref',), dict(required=False, type=str, default=None, help='URef of the stored contract to be called in the payment; base16 encoded')],
        [('-s', '--session'), dict(required=False, type=str, default=None, help='Path to the file with session code')],
        [('--session-hash',), dict(required=False, type=str, default=None, help='Hash of the stored contract to be called in the session; base16 encoded')],
        [('--session-name',), dict(required=False, type=str, default=None, help='Name of the stored contract (associated with the executing account) to be called in the session')],
        [('--session-uref',), dict(required=False, type=str, default=None, help='URef of the stored contract to be called in the session; base16 encoded')],
        [('--session-args',), dict(required=False, type=str, help="""JSON encoded list of session args, e.g.: '[{"name": "amount", "value": {"long_value": 123456}}]'""")],
        [('--payment-args',), dict(required=False, type=str, help="""JSON encoded list of payment args, e.g.: '[{"name": "amount", "value": {"big_int": {"value": "123456", "bit_width": 512}}}]'""")],
        [('--private-key',), dict(required=True, type=str, help='Path to the file with account public key (Ed25519)')],
        [('--public-key',), dict(required=True, type=str, help='Path to the file with account private key (Ed25519)')]]

    parser.addCommand('deploy', deploy_command, 'Deploy a smart contract source file to Casper on an existing running node. The deploy will be packaged and sent as a block to the network depending on the configuration of the Casper instance',
                      deploy_options)

    parser.addCommand('bond', bond_command, 'Issues bonding request',
                      [[('-a', '--amount'), dict(required=True, type=int, help='amount of motes to bond')]] + deploy_options)

    parser.addCommand('unbond', unbond_command, 'Issues unbonding request',
                      [[('-a', '--amount'),
                       dict(required=False, default=None, type=int, help='Amount of motes to unbond. If not provided then a request to unbond with full staked amount is made.')]] + deploy_options)

    parser.addCommand('propose', propose_command, 'Force a node to propose a block based on its accumulated deploys.', [])

    parser.addCommand('show-block', show_block_command, 'View properties of a block known by Casper on an existing running node. Output includes: parent hashes, storage contents of the tuplespace.',
                      [[('hash',), dict(type=str, help='the hash value of the block')]])

    parser.addCommand('show-blocks', show_blocks_command, 'View list of blocks in the current Casper view on an existing running node.',
                      [[('-d', '--depth'), dict(required=True, type=int, help='depth in terms of block height')]])

    parser.addCommand('show-deploy', show_deploy_command, 'View properties of a deploy known by Casper on an existing running node.',
                      [[('hash',), dict(type=str, help='Value of the deploy hash, base16 encoded.')]])

    parser.addCommand('show-deploys', show_deploys_command, 'View deploys included in a block.',
                      [[('hash',), dict(type=str, help='Value of the block hash, base16 encoded.')]])

    parser.addCommand('vdag', vdag_command, 'DAG in DOT format',
                      [[('-d', '--depth'), dict(required=True, type=int, help='depth in terms of block height')],
                       [('-o', '--out'), dict(required=False, type=str, help='output image filename, outputs to stdout if not specified, must end with one of the png, svg, svg_standalone, xdot, plain, plain_ext, ps, ps2, json, json0')],
                       [('-s', '--show-justification-lines'), dict(action='store_true', help='if justification lines should be shown')],
                       [('--stream',), dict(required=False, choices=('single-output', 'multiple-outputs'), help="subscribe to changes, '--out' has to be specified, valid values are 'single-output', 'multiple-outputs'")]])

    parser.addCommand('query-state', query_state_command, 'Query a value in the global state.',
                      [[('-b', '--block-hash'), dict(required=True, type=str, help='Hash of the block to query the state of')],
                       [('-k', '--key'), dict(required=True, type=str, help='Base16 encoding of the base key')],
                       [('-p', '--path'), dict(required=True, type=str, help="Path to the value to query. Must be of the form 'key1/key2/.../keyn'")],
                       [('-t', '--type'), dict(required=True, choices=('hash', 'uref', 'address', 'local'),
                                               help="Type of base key. Must be one of 'hash', 'uref', 'address' or 'local'. For 'local' key type, 'key' value format is {seed}:{rest}, where both parts are hex encoded.")]])

    parser.addCommand('balance', balance_command, 'Returns the balance of the account at the specified block.',
                      [[('-a', '--address'), dict(required=True, type=str, help="Account's public key in hex.")],
                       [('-b', '--block-hash'), dict(required=True, type=str, help='Hash of the block to query the state of')]])
    # fmt:on
    sys.exit(parser.run())


def check_bundled_contracts():
    print(dir(pkg_resources))
    p = pkg_resources.resource_filename(__name__, "bonding.wasm")
    if not os.path.exists(p):
        raise Exception(f"No bundled contract {p}")


if __name__ == "__main__":
    main()
