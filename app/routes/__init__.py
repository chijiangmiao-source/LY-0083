from .auth_routes import register_auth_routes
from .bath_area_routes import register_bath_area_routes
from .wristband_routes import register_wristband_routes
from .member_routes import register_member_routes
from .warning_routes import register_warning_routes
from .store_routes import register_store_routes
from .cross_store_routes import register_cross_store_routes
from .issue_routes import register_issue_routes
from .return_routes import register_return_routes
from .loss_routes import register_loss_routes
from .reissue_routes import register_reissue_routes
from .shift_routes import register_shift_routes
from .tracking_routes import register_tracking_routes


def register_all_routes(app):
    register_auth_routes(app)
    register_bath_area_routes(app)
    register_wristband_routes(app)
    register_member_routes(app)
    register_warning_routes(app)
    register_store_routes(app)
    register_cross_store_routes(app)
    register_issue_routes(app)
    register_return_routes(app)
    register_loss_routes(app)
    register_reissue_routes(app)
    register_shift_routes(app)
    register_tracking_routes(app)


__all__ = [
    'register_all_routes',
    'register_auth_routes',
    'register_bath_area_routes',
    'register_wristband_routes',
    'register_member_routes',
    'register_warning_routes',
    'register_store_routes',
    'register_cross_store_routes',
    'register_issue_routes',
    'register_return_routes',
    'register_loss_routes',
    'register_reissue_routes',
    'register_shift_routes',
    'register_tracking_routes',
]
