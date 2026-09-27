"""
Workflow module for Closed-Loop Automation.
Decouples Deal Collection, Category Routing, and Group Delivery Cycle.
"""

from .deal_collector import DealCollector
from .category_router import CategoryRouter
from .closed_loop_engine import ClosedLoopEngine
from .account_router import AccountRouter

__all__ = ["DealCollector", "CategoryRouter", "ClosedLoopEngine", "AccountRouter"]

