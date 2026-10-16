BEGIN TRANSACTION READ ONLY;
SELECT json_build_object(
  'postgres_version', current_setting('server_version'),
  'pgvector_version', (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
  'alembic_revision', (SELECT version_num FROM alembic_version),
  'table_counts', json_build_object(
    'users', (SELECT count(*) FROM users),
    'auth_sessions', (SELECT count(*) FROM auth_sessions),
    'knowledge_bases', (SELECT count(*) FROM knowledge_bases),
    'documents', (SELECT count(*) FROM documents),
    'storage_cleanup_tasks', (SELECT count(*) FROM storage_cleanup_tasks),
    'document_chunks', (SELECT count(*) FROM document_chunks),
    'conversations', (SELECT count(*) FROM conversations),
    'messages', (SELECT count(*) FROM messages),
    'usage_events', (SELECT count(*) FROM usage_events),
    'daily_usage_counters', (SELECT count(*) FROM daily_usage_counters)
  )
);
COMMIT;
