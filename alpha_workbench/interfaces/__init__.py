"""Cross-role interface definitions for Role5 ↔ Role2 / Role6 data exchange."""

from alpha_workbench.interfaces.role_interfaces import (
    Role5BacktestOutput,
    Role5ToRole2Payload,
    Role5ToRole6Payload,
    RoleInterfaceAdapter,
    create_backtest_output_for_roles,
    prepare_role2_storage_payload,
    prepare_role6_viz_payload,
)
