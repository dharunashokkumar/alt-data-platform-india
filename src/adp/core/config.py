"""Central configuration.

All env-driven knobs live here so deployment target (local docker-compose vs.
the Proxmox cluster) is a pure config change, never a code change.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="ADP_", extra="ignore"
    )

    # --- Postgres / TimescaleDB ---
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_db: str = "adp"
    pg_user: str = "adp"
    pg_password: str = "adp"

    # --- Object storage (MinIO / S3) ---
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    bronze_bucket: str = "bronze"

    # --- Market data ---
    market_data_provider: str = "yfinance"

    # --- POSOCO source ---
    # Discovery is configurable so a site/layout change is a config fix, not a
    # code fix. {yyyy} {mm} {dd} {ddmmyyyy} {ddmmyy} placeholders are supported.
    posoco_report_url_template: str = Field(
        default=(
            "https://report.grid-india.in/ReportDownload.aspx"
            "?dt={ddmmyyyy}&type=psp"
        )
    )
    # If set, the source reads `<dir>/posoco_<yyyy-mm-dd>.{csv,pdf}` instead of
    # hitting the network. Lets the whole pipeline run offline / in CI / from a
    # cleaned historical archive without any code change.
    posoco_local_dir: str | None = None

    # --- GST e-way bill source (monthly) ---
    # GSTN / e-way-bill portal monthly statistics. {yyyy} {mm} placeholders.
    # NOTE: GSTN portals change layout often — this is config precisely so a
    # site change is an env edit, not a code change.
    gst_report_url_template: str = Field(
        default=(
            "https://ewaybillgst.gov.in/Others/Statistics/"
            "EWB_{yyyy}{mm}.xlsx"
        )
    )
    # If set, reads `<dir>/gst_<yyyy-mm>.{xlsx,pdf,csv}` (real archived files).
    gst_local_dir: str | None = None
    # The monthly e-way-bill statistics are released ~12 days into the next
    # month; published_date = month_end + this many days (PIT correctness).
    gst_publication_lag_days: int = 12

    # --- Indian Railways freight source (monthly) ---
    railway_report_url_template: str = Field(
        default=(
            "https://www.indianrailways.gov.in/railwayboard/"
            "uploads/directorate/stat_econ/Freight_{yyyy}{mm}.pdf"
        )
    )
    # If set, reads `<dir>/railway_<yyyy-mm>.{pdf,csv}` (real archived files).
    railway_local_dir: str | None = None
    # Ministry-of-Railways monthly freight figures are released within ~3 days
    # of month end; published_date = month_end + this many days.
    railway_publication_lag_days: int = 3

    @property
    def pg_dsn(self) -> str:
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
