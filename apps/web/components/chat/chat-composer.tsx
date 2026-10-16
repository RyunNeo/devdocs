"use client";
import { Send, Square } from "lucide-react";
import { useRef } from "react";

export function ChatComposer({ value, onChange, busy, disabled, onSend, onStop }: {
  value: string; onChange: (value: string) => void; busy: boolean; disabled: boolean;
  onSend: () => void; onStop: () => void;
}) {
  const composing = useRef(false);
  return <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); onSend(); }}>
    <textarea aria-label="问题" placeholder="输入你的问题" maxLength={2000} rows={3} value={value}
      disabled={busy || disabled} onChange={(event) => onChange(event.target.value)}
      onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
      onKeyDown={(event) => {
        if (composing.current || event.nativeEvent.isComposing || event.keyCode === 229) return;
        if (event.key !== "Enter" || event.shiftKey) return;
        event.preventDefault();
        if (event.repeat || event.ctrlKey || event.altKey || event.metaKey || busy || disabled || !value.trim()) return;
        event.currentTarget.form?.requestSubmit();
      }} />
    <div className="chat-composer-actions"><span className="quiet-label">{value.length} / 2000</span>
      {busy ? <button type="button" className="icon-button" aria-label="停止生成" title="停止生成" onClick={onStop}><Square size={19} /></button>
        : <button className="icon-button chat-send" type="submit" aria-label="发送问题" title="发送问题" disabled={disabled || !value.trim()}><Send size={19} /></button>}
    </div>
  </form>;
}
