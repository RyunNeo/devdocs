"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="connection-error"><h1>页面暂时无法加载</h1><p>请稍后重试。</p><button className="primary-button" onClick={reset}>重试</button></main>;
}
