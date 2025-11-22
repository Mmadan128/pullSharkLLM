import logging
import os
import pathway as pw
from dotenv import load_dotenv

from pathway.udfs import DefaultCache
from pathway.udfs import ExponentialBackoffRetryStrategy
from pathway.xpacks.llm.question_answering import BaseRAGQuestionAnswerer
from pathway.stdlib.indexing import UsearchKnnFactory, USearchMetricKind
from pathway.xpacks.llm import embedders, llms, parsers, splitters
from pathway.xpacks.llm.document_store import DocumentStore

from data.connector.githubConnector import GitHubIssueScraperSubject

# Pathway License
pw.set_license_key("demo-license-key-with-telemetry")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

load_dotenv()

# Issue Schema
class IssueSchema(pw.Schema):
    url: str = pw.column_definition(primary_key=True)
    data: str
    _metadata: dict



def run():

    # ------------------ CONNECTOR (GitHub Closed Issues) ------------------
    github_input = pw.io.python.read(
        GitHubIssueScraperSubject(
            scrap_link="https://api.github.com/repos/RocketChat/Rocket.Chat/issues"
        ),
        schema=IssueSchema,
    )

    sources = [github_input]

    # ------------------ PARSER ------------------
    # DoclingParser supports text + images + layout
    parser = parsers.Utf8Parser()

    # ------------------ TEXT SPLITTER ------------------
    text_splitter = splitters.TokenCountSplitter(
        max_tokens=800
    )

    # ------------------ EMBEDDING MODEL ------------------
    embedder = embedders.GeminiEmbedder(
        model="models/text-embedding-004"
    )

    # ------------------ VECTOR INDEX ------------------
    index = UsearchKnnFactory(
        reserved_space=3000,
        embedder=embedder,
        metric=USearchMetricKind.COS,
    )

    # ------------------ LLM ------------------
    llm = llms.LiteLLMChat(
        model="gemini/gemini-2.0-flash",
        cache_strategy=DefaultCache(),
        retry_strategy=ExponentialBackoffRetryStrategy(max_retries=2),
        temperature=0,
        capacity=8,
    )

    # ------------------ DOCUMENT STORE ------------------
    doc_store = DocumentStore(
        docs=sources,
        splitter=text_splitter,
        parser=parser,
        retriever_factory=index,
    )

    # ------------------ RAG APP ------------------
    rag_app = BaseRAGQuestionAnswerer(
        llm=llm,
        indexer=doc_store
    )

    # ------------------ SERVER ------------------
    host = "0.0.0.0"
    port = int(os.environ.get("PATHWAY_PORT", 8000))

    rag_app.build_server(host=host, port=port)

    rag_app.run_server(
        with_cache=True,
        terminate_on_error=True
    )


if __name__ == "__main__":
    run()
