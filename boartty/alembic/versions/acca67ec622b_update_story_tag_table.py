"""update story_tag table

Revision ID: acca67ec622b
Revises: 183755ac91df
Create Date: 2017-11-27 10:49:04.902131

"""

# revision identifiers, used by Alembic.
revision = 'acca67ec622b'
down_revision = '183755ac91df'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_index(op.f('story_tag_unique'), 'story_tag',
                    ['story_key', 'tag_key'], unique=True)


def downgrade():
    pass
