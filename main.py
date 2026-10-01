import os
import json
import struct
from urllib.parse import quote_plus
from langchain.agents.structured_output import ProviderStrategy

import sqlglot
from sqlglot import exp
from dotenv import load_dotenv
from pydantic import BaseModel
from sqlalchemy import create_engine, event
#from azure.identity import InteractiveBrowserCredential
from azure.identity import DefaultAzureCredential

from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain.tools import tool


# STEP 1: Load the settings from your .env file
load_dotenv()


# STEP 2: Pick the AI model (Claude)
model = init_chat_model(os.environ["MODEL_NAME"])


# STEP 3: Connect to Microsoft Fabric
# Your browser opens once so you can sign in with your Fabric account.
# credential = InteractiveBrowserCredential(login_hint=os.environ["FABRIC_USER"])
credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)

connection_string = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={os.environ['FABRIC_SERVER']},1433;"
    f"DATABASE={os.environ['FABRIC_DATABASE']};"
    "Encrypt=yes;"
)

engine = create_engine(
    f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}",
    ignore_no_transaction_on_rollback=True,
)


# Every time we connect, hand the driver a sign-in pass from the browser login
@event.listens_for(engine, "do_connect")
def add_sign_in_pass(dialect, conn_rec, cargs, cparams):
    token = credential.get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("utf-16-le")
    cparams["attrs_before"] = {
        1256: struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    }


# STEP 4: The tool the AI uses to run SQL
# It checks the query first, then runs it and sends back the real data.
@tool
def run_sql(query: str) -> str:
    """Run a SELECT query on dbo.sales_clean and return the results."""

    # Read the SQL so we can check it
    statements = sqlglot.parse(query, read="tsql")

    # Check 1: only one query, and it must be a SELECT
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return "Only one SELECT query is allowed."

    # Check 2: the only real table it can use is sales_clean
    query_tree = statements[0]
    temp_tables = {cte.alias.lower() for cte in query_tree.find_all(exp.CTE)}
    tables_used = {table.name.lower() for table in query_tree.find_all(exp.Table)}
    if tables_used - temp_tables != {"sales_clean"}:
        return "You can only query dbo.sales_clean."

    # Run the query and return up to 200 rows
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(query).fetchmany(200)
    return json.dumps([dict(row._mapping) for row in rows], default=str)


# STEP 5: The shape of every answer
# The AI must give the answer AND the SQL it used, so you can check its work.
class SalesAnswer(BaseModel):
    answer: str
    sql_used: list[str]


# STEP 6: Build the agent
agent = create_agent(
    model=model,
    tools=[run_sql],
    response_format=ProviderStrategy(SalesAnswer),
    system_prompt="""
You are a sales analyst. Answer questions using the run_sql tool.

Table: dbo.sales_clean
Columns: order_id, order_date, store, product, category, units, unit_price, discount_pct, Revenue

Rules:
- Write Microsoft T-SQL. Use TOP instead of LIMIT.
- Only submit your final answer after you have seen the SQL results.
- Every number in your answer must come from the SQL results. Never guess.
- If the data can't answer the question, say so.
""",
)


# STEP 7: Ask questions in the terminal
if __name__ == "__main__":

    # Sign in once before the agent starts (your browser will open)
    with engine.connect() as conn:
        count = conn.exec_driver_sql("SELECT COUNT(*) FROM dbo.sales_clean").scalar()
        print(f"Connected to Fabric. Rows in sales_clean: {count}")

    while True:
        question = input("\nAsk a sales question (or 'exit'): ").strip()
        if question.lower() == "exit":
            break

        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
        ans = result["structured_response"]

        print(f"\n{ans.answer}\n")
        print("SQL used:", *ans.sql_used, sep="\n")