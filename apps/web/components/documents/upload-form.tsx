"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { LoaderCircle, Upload, Square } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { DocumentRecord } from "@/lib/documents";
import { useDocumentBatch } from "./use-document-batch";
import { BatchResults } from "./batch-results";

function invalidFile(file: File) {
  if (!/\.(md|txt|pdf)$/i.test(file.name)) return "目前只支持 Markdown (.md)、TXT (.txt) 和文本 PDF (.pdf)";
  if (!file.size) return "文件为空，请选择有内容的文件";
  if (file.size > 10 * 1024 * 1024) return "单个文件不能超过 10 MiB";
  return "";
}

export function UploadForm({ knowledgeBaseId, disabled, onUploaded, onBusyChange }: {
  knowledgeBaseId: string; disabled: boolean; onUploaded: (docs: DocumentRecord[]) => void; onBusyChange: (busy: boolean) => void;
}) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const restoreFocus = useRef(false);
  const [files, setFiles] = useState<File[]>([]);
  const [retryFiles, setRetryFiles] = useState<File[]>([]);
  const [error, setError] = useState("");
  const batch = useDocumentBatch();
  const pending = batch.running;
  const rejectedFiles = files.map(file => ({ name: file.name, reason: invalidFile(file) })).filter(file => file.reason);

  useEffect(() => {
    if (restoreFocus.current && !pending && !disabled) {
      inputRef.current?.focus(); restoreFocus.current = false;
    }
  }, [pending, disabled]);

  function choose(candidates: File[]) {
    batch.reset(); setError(""); setRetryFiles([]); setFiles([]);
    if (candidates.length > 20) { setError("一次最多选择 20 个文件，请分批上传"); return; }
    setFiles(candidates);
    if (candidates.length === 1) setError(invalidFile(candidates[0]));
  }

  async function upload(candidates: File[]) {
    if (inFlight.current || disabled || !candidates.some(file => !invalidFile(file))) return;
    inFlight.current = true; onBusyChange(true); setError("");
    const uploaded: DocumentRecord[] = [];
    try {
      const results = await batch.start(candidates.map((file, index) => ({
        id: String(index), label: file.name, skip: invalidFile(file),
        unknownMessage: "暂时无法确认上传结果，请刷新文档列表确认后再重试",
        execute: async (signal: AbortSignal) => {
          const body = new FormData(); body.append("file", file);
          const result = await apiRequest<DocumentRecord>(`/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents`, body,
            AbortSignal.any([signal, AbortSignal.timeout(30000)]));
          uploaded.push(result);
          return result.status === "parsed" ? "已上传并解析" : `已保存，解析失败：${result.error_message ?? "请查看文档详情"}`;
        },
      })));
      if (!results) return;
      restoreFocus.current = true;
      setFiles([]);
      setRetryFiles(candidates.filter((_, index) => results[index].state === "failed"));
      if (inputRef.current) inputRef.current.value = "";
      onUploaded(uploaded);
    } finally {
      inFlight.current = false; onBusyChange(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void upload(files); }

  return (
    <form className="upload-form" onSubmit={submit} aria-busy={pending}>
      <div className="upload-file-field">
        <label htmlFor={id}>选择文档</label>
        <input ref={inputRef} id={id} type="file" multiple accept=".md,.txt,.pdf" disabled={pending || disabled}
          onChange={(event) => choose(Array.from(event.target.files ?? []))} aria-describedby={`${id}-constraints`} />
        <small id={`${id}-constraints`}>MD / TXT（UTF-8）/ 文本 PDF · 单文件 ≤ 10 MiB · 每批 ≤ 20 个</small>
      </div>
      <button className="primary-button" disabled={!files.some(file => !invalidFile(file)) || pending || disabled} type="submit">
        {pending ? <LoaderCircle size={17} className="spinner" aria-hidden="true" /> : <Upload size={17} aria-hidden="true" />}
        {pending ? "上传并解析中" : "上传文档"}
      </button>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="upload-batch-results">
        {files.length > 1 && rejectedFiles.length > 0 ? <ul className="batch-result-list" aria-label="文件校验结果">{rejectedFiles.map((file, index) =>
          <li key={index} role="alert"><strong>{file.name}</strong><p>{file.reason}</p></li>)}</ul> : null}
        <BatchResults results={batch.results} running={pending} label="上传结果" />
        {pending ? <button type="button" className="secondary-button" disabled={batch.stopping} onClick={batch.stop}><Square size={15} aria-hidden="true" />{batch.stopping ? "等待当前文件完成" : "停止后续上传"}</button> : null}
        {!pending && retryFiles.length ? <button type="button" className="secondary-button" disabled={disabled} onClick={() => void upload(retryFiles)}>重试失败项</button> : null}
      </div>
    </form>
  );
}
