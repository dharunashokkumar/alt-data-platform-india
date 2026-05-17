"""initial schema: universe, silver_observations, features, signals

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE universe (
            ticker  text PRIMARY KEY,
            name    text NOT NULL,
            sector  text,
            state   text
        );

        -- Generic silver layer: source-specific dims live in jsonb so adding
        -- a new source needs NO migration.
        CREATE TABLE silver_observations (
            id               bigserial PRIMARY KEY,
            obs_key          text UNIQUE NOT NULL,
            source           text NOT NULL,
            observation_date date NOT NULL,
            published_date   date NOT NULL,
            dimensions       jsonb NOT NULL,
            value            double precision NOT NULL,
            unit             text NOT NULL,
            bronze_uri       text NOT NULL,
            ingested_at      timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_silver_source_date
            ON silver_observations (source, observation_date);
        CREATE INDEX ix_silver_dims
            ON silver_observations USING gin (dimensions);

        -- Gold feature store. The PK includes published_date so multiple
        -- vintages of the same feature coexist; PIT reads pick the latest
        -- vintage known at as_of.
        CREATE TABLE features (
            ticker         text NOT NULL,
            feature_date   date NOT NULL,
            feature_name   text NOT NULL,
            value          double precision NOT NULL,
            as_of_date     date NOT NULL,
            published_date date NOT NULL,
            source         text NOT NULL,
            source_version text NOT NULL DEFAULT 'v1',
            ingested_at    timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (ticker, feature_date, feature_name, published_date)
        );
        CREATE INDEX ix_features_pit
            ON features (feature_name, published_date, feature_date);

        CREATE TABLE signals (
            ticker         text NOT NULL,
            signal_date    date NOT NULL,
            signal_name    text NOT NULL,
            score          double precision NOT NULL,
            published_date date NOT NULL,
            model_version  text NOT NULL DEFAULT 'v1',
            created_at     timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (ticker, signal_date, signal_name, published_date)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS signals;
        DROP TABLE IF EXISTS features;
        DROP TABLE IF EXISTS silver_observations;
        DROP TABLE IF EXISTS universe;
        """
    )
