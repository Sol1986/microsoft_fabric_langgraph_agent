# Fabric Sales Agent

An AI sales analyst that answers plain-English questions about your sales data in Microsoft Fabric. It writes T-SQL, runs it against `dbo.sales_clean`, and returns an answer along with the SQL it used so you can check its work.

## How it works

- **Model:** Claude, through LangChain (`MODEL_NAME` in `.env`).
- **Data:** connects to your Fabric SQL endpoint over ODBC, using Azure sign-in (browser login or a service principal).
- **Safety:** every query is checked with `sqlglot` before it runs. Only a single `SELECT` on `sales_clean` is allowed, and results are capped at 200 rows.
- **Answers:** each reply includes the answer and the SQL queries behind it.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- A Microsoft Fabric workspace with a `dbo.sales_clean` table
- An Anthropic API key

## Setup

```bash
uv sync
cp example.env .env   # then fill in your values
```

## Run it

**In the terminal:**

```bash
uv run main.py
```

Your browser opens once to sign in to Fabric, then you can type questions. Type `exit` to quit.

**In LangGraph Studio:**

```bash
uv run langgraph dev
```

This loads the `sales_agent` graph defined in `langgraph.json`.

## Example questions

- Which store had the highest revenue last month?
- What are the top 5 products by units sold?
- What's the average discount by category?
