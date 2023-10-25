from typing import Union

from iconsdk.builder.call_builder import CallBuilder
from iconsdk.icon_service import IconService
from iconsdk.providers.http_provider import HTTPProvider

from icx_reward.types.constants import SYSTEM_ADDRESS
from icx_reward.types.prep import PRep


class RPC:
    def __init__(self, uri: str):
        self.__sdk = IconService(HTTPProvider(uri, request_kwargs={"timeout": 120}))

    @property
    def sdk(self) -> IconService:
        return self.__sdk

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

    def term(self, height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getPRepTerm",
            height=height,
        )

    def get_prep(self, address: str, height: int = None, to_obj: bool = False) -> Union[dict, PRep]:
        resp = self.call(
            to=SYSTEM_ADDRESS,
            method="getPRep",
            params={"address": address},
            height=height,
        )
        if to_obj:
            return PRep.from_dict(resp)
        else:
            return resp

    def get_bond(self, address: str, height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getBond",
            params={"address": address},
            height=height,
        )

    def get_delegation(self, address: str, height: int = None):
        return self.call(
            to=SYSTEM_ADDRESS,
            method="getDelegation",
            params={"address": address},
            height=height,
        )
