import { BookOpen } from "lucide-react";
import Link from "next/link";

export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="DevDocs AI 首页">
      <span className="brand-mark"><BookOpen size={21} aria-hidden="true" /></span>
      <span>DevDocs <span className="brand-ai">AI</span></span>
    </Link>
  );
}
