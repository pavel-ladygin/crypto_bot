from .list import router as list_router
from .add import router as add_router
from .start import router as start_router
from .dell import router as dell_router
from .help import router as help_router

all_router = [list_router, add_router, start_router, dell_router, help_router]