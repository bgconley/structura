import {useState} from "react";
import {fetchJson} from "./api";
import {getParseDebug} from "./parseDebugApi";
import {getCurrentSemanticAnnotation} from "./semanticAnnotationApi";
import {useKeyedRequest} from "./useKeyedRequest";
import type {DocumentDetail} from "./types";

export function useDocumentWorkspace(documentId: string | null, visit: string) {
  const key = documentId ? `${documentId}:${visit}` : null;
  const [parseKey, setParseKey] = useState<string | null>(null);
  const [semanticKey, setSemanticKey] = useState<string | null>(null);
  const detail = useKeyedRequest(key, async (signal) => {
    const next = await fetchJson<DocumentDetail>(`/api/v1/documents/${documentId}`, {signal});
    if (next.id !== documentId) throw new Error("The returned document did not match this link. Please retry.");
    return next;
  });
  const parse = useKeyedRequest(key && parseKey === key ? key : null, async (signal) => {
    const next = await getParseDebug(documentId!, signal);
    if (next.document.id !== documentId) throw new Error("Parse details did not match this document.");
    return next;
  });
  const semantic = useKeyedRequest(key && semanticKey === key ? key : null, async (signal) => {
    const next = await getCurrentSemanticAnnotation(documentId!, "smart", signal);
    if (next.documentId !== documentId) throw new Error("Smart Parse details did not match this document.");
    if (!next.current) throw new Error("No Smart Parse manifest has been persisted yet.");
    return next.current;
  });
  return {detail, parse, semantic,
    loadParse: (id: string) => {
      if (id !== documentId || !detail.data) return;
      if (parseKey === key) void parse.reload(); else setParseKey(key);
    },
    loadSemantic: (id: string) => {
      if (id !== documentId || !detail.data) return;
      if (semanticKey === key) void semantic.reload(); else setSemanticKey(key);
    },
  };
}
