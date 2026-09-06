"""sync models with schema

Revision ID: 7e6c5aeef477
Revises: 293138585702
Create Date: 2026-08-14 14:53:20.739087+00:00

仅补齐模型与库表的真实差异（meetings.transcription_mode），
不删除任何既有索引 / 外键约束（避免破坏 ivfflat 向量索引等）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e6c5aeef477'
down_revision: Union[str, None] = '293138585702'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('meetings', sa.Column('transcription_mode', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('meetings', 'transcription_mode')
