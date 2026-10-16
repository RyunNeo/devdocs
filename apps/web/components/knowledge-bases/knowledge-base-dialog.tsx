"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, X } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { KnowledgeBase } from "@/lib/knowledge-bases";

export function KnowledgeBaseDialog({ knowledgeBase, onDismiss, onSaved }: {
  knowledgeBase?: KnowledgeBase;
  onDismiss: () => void;
  onSaved: () => void;
}) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const id = useId();
  const [name, setName] = useState(knowledgeBase?.name ?? "");
  const [description, setDescription] = useState(knowledgeBase?.description ?? "");
  const [pending, setPending] = useState(false);
  const [fieldError, setFieldError] = useState("");
  const [error, setError] = useState("");
  const editing = knowledgeBase !== undefined;
  const changed = !knowledgeBase || name.trim() !== knowledgeBase.name
    || description !== (knowledgeBase.description ?? "");

  useEffect(() => {
    if (!dialogRef.current?.open) dialogRef.current?.showModal();
    nameRef.current?.focus();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const normalizedName = name.trim();
    if (!normalizedName) {
      setFieldError("请输入知识库名称");
      nameRef.current?.focus();
      return;
    }
    setFieldError("");
    setError("");
    const payload: { name?: string; description?: string | null } = {};
    if (!knowledgeBase || normalizedName !== knowledgeBase.name) payload.name = normalizedName;
    if (!knowledgeBase || description !== (knowledgeBase.description ?? "")) {
      payload.description = description.trim() ? description : null;
    }
    if (Object.keys(payload).length === 0) return;
    inFlight.current = true;
    setPending(true);
    try {
      await apiRequest<KnowledgeBase>(
        knowledgeBase ? `/knowledge-bases/${encodeURIComponent(knowledgeBase.id)}` : "/knowledge-bases",
        payload, AbortSignal.timeout(15000), editing ? "PATCH" : "POST",
      );
      inFlight.current = false;
      dialogRef.current?.close();
      onSaved();
    } catch (failure) {
      inFlight.current = false;
      if (failure instanceof ApiError && failure.status === 401) {
        dialogRef.current?.close();
        router.replace("/login");
        router.refresh();
        return;
      }
      setError(failure instanceof ApiError && failure.status === 0
        ? `暂时无法确认${editing ? "保存" : "创建"}结果，请刷新列表确认后再重试`
        : failure instanceof Error ? failure.message : "操作失败，请重试");
      setPending(false);
    }
  }

  return (
    <dialog ref={dialogRef} className="knowledge-dialog" aria-labelledby={`${id}-title`}
      onClose={onDismiss} onCancel={(event) => { if (inFlight.current) event.preventDefault(); }}>
      <div className="dialog-heading">
        <h2 id={`${id}-title`}>{editing ? "编辑知识库" : "创建知识库"}</h2>
        <button type="button" className="icon-button" aria-label="关闭弹窗" title="关闭弹窗"
          disabled={pending} onClick={() => dialogRef.current?.close()}><X size={19} aria-hidden="true" /></button>
      </div>
      <form onSubmit={submit} className="knowledge-form" aria-busy={pending}>
        <div className="field">
          <label htmlFor={`${id}-name`}>名称</label>
          <input ref={nameRef} id={`${id}-name`} value={name} onChange={(event) => {
            setName(event.target.value); setFieldError("");
          }} maxLength={80} required disabled={pending} autoComplete="off" placeholder="例如：Python 学习"
            aria-invalid={fieldError ? true : undefined} aria-describedby={fieldError ? `${id}-name-error` : undefined} />
          {fieldError ? <p id={`${id}-name-error`} role="alert" className="form-error">{fieldError}</p> : null}
        </div>
        <div className="field">
          <label htmlFor={`${id}-description`}>描述</label>
          <textarea id={`${id}-description`} value={description} onChange={(event) => setDescription(event.target.value)}
            maxLength={1000} rows={4} disabled={pending} placeholder="可选，记录这个知识库的学习主题" />
          <small className="description-count">{description.length} / 1000</small>
        </div>
        {error ? <p role="alert" className="form-error">{error}</p> : null}
        <div className="dialog-actions">
          <button type="button" className="secondary-button" disabled={pending} onClick={() => dialogRef.current?.close()}>取消</button>
          <button type="submit" className="primary-button" disabled={pending || (editing && !changed)}>
            {pending ? <LoaderCircle size={17} className="spinner" aria-hidden="true" /> : null}
            {editing ? pending ? "正在保存" : "保存" : pending ? "正在创建" : "创建"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
