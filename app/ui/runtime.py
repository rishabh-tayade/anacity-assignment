"""Shared app setup: builds the container once per server process."""

from datetime import date

import streamlit as st
from dotenv import load_dotenv

from moveflow.container import Container, build_container
from moveflow.demo.seed import seed_demo_data
from moveflow.llm.factory import build_llm_client
from moveflow.repositories.sqlite_repository import SqliteRequestRepository
from ui import ROOT

DB_PATH = ROOT / "data" / "moveflow.db"


@st.cache_resource
def get_container() -> Container:
    load_dotenv(ROOT / ".env")
    repository = SqliteRequestRepository(DB_PATH)
    seed_demo_data(repository, date.today())
    return build_container(repository, build_llm_client())
