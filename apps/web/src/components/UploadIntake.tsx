import {useState} from "react";
import type {UploadPolicy, UploadSource} from "../uploads/types";
import {uploadFileByteLimit} from "../uploads/queue";

function policyDescription(policy: UploadPolicy): string {
  const bytes = uploadFileByteLimit(policy);
  const size = bytes % 1048576 === 0 ? `${bytes / 1048576} MiB` : bytes % 1024 === 0 ? `${bytes / 1024} KiB` : `${bytes.toLocaleString()} bytes`;
  const labels: Record<string, string> = {"application/pdf": "PDF", "image/png": "PNG", "image/jpeg": "JPEG", "image/tiff": "TIFF", "image/webp": "WebP"};
  return `Max ${size} per file · ${policy.mimeTypes.map((mime) => labels[mime] ?? mime).join(", ")}`;
}

export type UploadIntakeProps = {policy: UploadPolicy | null; onFiles: (files: File[], source?: UploadSource) => Promise<void>};
export function UploadIntake({policy, onFiles, label = "Upload", source = "web_upload", className = "command-button"}:
  UploadIntakeProps & {label?: string; source?: UploadSource; className?: string}) {
  return <label className={className} title={policy ? policyDescription(policy) : undefined}>{label}<input type="file" multiple disabled={!policy?.available}
    aria-description={policy ? policyDescription(policy) : undefined}
    accept={policy?.mimeTypes.join(",") ?? ""} onChange={(event) => {
      const files = Array.from(event.currentTarget.files ?? []); event.currentTarget.value = "";
      if (files.length) void onFiles(files, source);
    }} /></label>;
}
export function UploadDropArea({policy, onFiles}: UploadIntakeProps) {
  const [dragging, setDragging] = useState(false), [notice, setNotice] = useState<string | null>(null);
  return <section className="upload-drop-area" aria-label="Add files to upload" data-dragging={dragging}
    onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
    onDrop={(event) => {
      event.preventDefault(); setDragging(false);
      if (!policy?.available) { setNotice("Upload policy is unavailable. Retry policy before adding files."); return; }
      const items = Array.from(event.dataTransfer.items);
      const directories = items.filter((item) => item.webkitGetAsEntry?.()?.isDirectory).length;
      setNotice(directories ? `${directories} folders were not added. Select individual files; folders are not expanded.` : null);
      const files = items.length ? items.filter((item) => !item.webkitGetAsEntry?.()?.isDirectory).map((item) => item.getAsFile()).filter((file): file is File => !!file)
        : Array.from(event.dataTransfer.files);
      if (files.length) void onFiles(files, "bulk_import");
    }}>
    <p>Drop PDF or image files here, or choose files. Originals are accepted before background processing finishes.</p>
    <UploadIntake policy={policy} onFiles={onFiles} label="Choose files" source="bulk_import" />
    {policy ? <p className="upload-retention-note">{policyDescription(policy)}</p> : null}
    {notice ? <p role="alert">{notice}</p> : null}
  </section>;
}
