from time import sleep

from typing import Union

from iconsdk.builder.call_builder import CallBuilder
from iconsdk.builder.transaction_builder import CallTransactionBuilder, TransactionBuilder
from iconsdk.exception import JSONRPCException
from iconsdk.icon_service import IconService
from iconsdk.providers.http_provider import HTTPProvider
from iconsdk.signed_transaction import SignedTransaction
from iconsdk.wallet.wallet import KeyWallet

from icx_reward.types.address import Address
from icx_reward.types.constants import SYSTEM_ADDRESS
from icx_reward.types.prep import PRep


class RPCBase:
    def __init__(self, uri: str):
        self.__uri = uri
        self.__sdk = IconService(HTTPProvider(uri, request_kwargs={"timeout": 120}))

    @property
    def uri(self) -> str:
        return self.__uri

    @property
    def sdk(self) -> IconService:
        return self.__sdk

    def transfer(self,
                 wallet: KeyWallet,
                 to_: str,
                 value: int,
             ):
        tx = TransactionBuilder().from_(wallet.get_address()) \
            .to(to_) \
            .step_limit(1000000) \
            .nid(1) \
            .value(value) \
            .build()

        signed_tx = SignedTransaction(tx, wallet)

        tx_hash = self.sdk.send_transaction(signed_tx)
        return tx_hash

    def call(self,
             method: str,
             params: dict = {},
             to: str = SYSTEM_ADDRESS,
             height: int = None,
             ) -> Union[dict, str]:
        cb = CallBuilder() \
            .to(to) \
            .method(method) \
            .params(params) \
            .height(height) \
            .build()
        return self.__sdk.call(cb)

    def invoke(self,
               wallet: KeyWallet,
               method: str,
               params: dict = {},
               to_: str = SYSTEM_ADDRESS):
        tx = CallTransactionBuilder().from_(wallet.get_address()) \
            .to(to_) \
            .step_limit(1000000) \
            .nid(1) \
            .method(method) \
            .params(params) \
            .build()

        signed_tx = SignedTransaction(tx, wallet)

        tx_hash = self.sdk.send_transaction(signed_tx)
        return tx_hash

    def wait_tx_confirm(self, tx_hash: str) -> dict:
        block_interval = 2
        i = 0
        while True:
            try:
                tx_result = self.sdk.get_transaction_result(tx_hash)
            except JSONRPCException:
                if i == 10:
                    assert False, f"waited {i} * {block_interval} sec and failed to get tx result for {tx_hash}"
                sleep(block_interval)
                i += 1
            else:
                return tx_result


class RPC(RPCBase):
    def __init__(self, uri: str):
        super().__init__(uri)

    def query_iscore(self,
                     address: str,
                     height: int = None,
                     ) -> dict:
        return self.call(
            to=SYSTEM_ADDRESS,
            method="queryIScore",
            params={"address": address},
            height=height,
        )

    def claim_iscore(self, wallet: KeyWallet) -> str:
        return self.invoke(wallet=wallet, method="claimIScore")

    def term(self, height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getPRepTerm",
            height=height,
        )

    def get_prep(self, address: Union[str, Address], height: int = None, to_obj: bool = False) -> Union[dict, PRep, None]:
        try:
            resp = self.call(
                to=SYSTEM_ADDRESS,
                method="getPRep",
                params={"address": address if isinstance(address, str) else str(address)},
                height=height,
            )
        except JSONRPCException:
            return None
        if to_obj:
            return PRep.from_dict(resp)
        else:
            return resp

    def set_stake(self, wallet: KeyWallet, amount: int):
        return self.invoke(
            wallet=wallet,
            method="setStake",
            params={"value": hex(amount)},
        )

    def get_stake(self, address: Union[str, Address], height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getStake",
            params={"address": address if isinstance(address, str) else str(address)},
            height=height,
        )

    def get_bond(self, address: Union[str, Address], height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getBond",
            params={"address": address if isinstance(address, str) else str(address)},
            height=height,
        )

    def get_delegation(self, address: [str, Address], height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getDelegation",
            params={"address": address if isinstance(address, str) else str(address)},
            height=height,
        )

    def get_network_info(self, height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getNetworkInfo",
            height=height,
        )
