"""卡4适配层；真实产品绑定与生命周期签收状态见 docs/integrations。"""
from .native import NativeAdapter
from .transports import HTTPTransport, SubprocessTransport, TransportError

__all__ = ["NativeAdapter", "SubprocessTransport", "HTTPTransport", "TransportError"]
