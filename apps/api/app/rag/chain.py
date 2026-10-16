from sqlalchemy import select

from app.models.message import Message
from app.rag import embeddings
from app.rag.prompts import build_retrieval_query
from app.rag.retriever import has_sources, retrieve_sources
from app.schemas.conversation import MessageRead


def prepare_context(factory, run):
    with factory() as db:
        history = [
            MessageRead.model_validate(m)
            for m in db.scalars(
                select(Message)
                .where(
                    Message.conversation_id == run.conversation_id,
                    Message.sequence < run.user_sequence,
                )
                .order_by(Message.sequence.desc())
                .limit(40)
            )
        ]
        history.reverse()
        available = has_sources(db, run.user_id, run.knowledge_base_id)
        return history, available


async def embed_question(settings, question, history):
    return await embeddings.make_embeddings(settings).aembed_query(
        build_retrieval_query(question, history)
    )


def query_context(factory, run, vector, settings):
    with factory() as db:
        return retrieve_sources(db, run.user_id, run.knowledge_base_id, vector, settings)
