"""Database connection managers for PostgreSQL and Neo4j."""

import os
from contextlib import contextmanager
from typing import Generator
from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver
from psycopg_pool import ConnectionPool

load_dotenv()

PG_USER = os.getenv("POSTGRES_USER", "transiq")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "transiq_secret")
PG_DB = os.getenv("POSTGRES_DB", "transiq_db")
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
CONN_STR = f"dbname={PG_DB} user={PG_USER} password={PG_PASS} host={PG_HOST} port={PG_PORT}"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "transiq_secret")

# Global instances
pg_pool = ConnectionPool(conninfo=CONN_STR, min_size=2, max_size=10, open=True)
neo4j_driver: Driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


@contextmanager
def get_pg_connection():
    with pg_pool.connection() as conn:
        yield conn


def get_neo4j_session():
    return neo4j_driver.session()


def close_connections():
    pg_pool.close()
    neo4j_driver.close()
