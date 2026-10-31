from alembic import context
from sqlalchemy import create_engine

from dataflow.bootstrap import models  # noqa: F401
from dataflow.platform.config import get_settings
from dataflow.platform.database import Base

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(
        get_settings().database_url, connect_args={"connect_timeout": 5}
    ).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
