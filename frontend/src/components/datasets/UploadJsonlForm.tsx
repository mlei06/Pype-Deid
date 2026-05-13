import { useState } from 'react';
import { Loader2, Upload } from 'lucide-react';
import { ApiError } from '../../api/client';
import { useUploadDataset } from '../../hooks/useDatasets';

interface UploadJsonlFormProps {
  onRegistered: (name: string) => void;
}

export default function UploadJsonlForm({ onRegistered }: UploadJsonlFormProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mutation = useUploadDataset();

  const handleSubmit = () => {
    if (!name.trim() || !file) return;
    setError(null);
    mutation.mutate(
      {
        name: name.trim(),
        file,
        description: description.trim() || undefined,
        lineFormat: 'annotated_jsonl',
      },
      {
        onSuccess: (d) => {
          onRegistered(d.name);
          setName('');
          setDescription('');
          setFile(null);
        },
        onError: (e) => {
          if (e instanceof ApiError) {
            const d = e.detail;
            setError(typeof d === 'string' ? d : JSON.stringify(d));
          } else {
            setError(e instanceof Error ? e.message : 'Upload failed');
          }
        },
      },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-corpus"
            className="w-full min-w-0 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-gray-500 focus:ring-1 focus:ring-gray-500 focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Description</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="optional"
            className="w-full min-w-0 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-gray-500 focus:ring-1 focus:ring-gray-500 focus:outline-none"
          />
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500">JSONL file</label>
        <input
          type="file"
          accept=".jsonl,application/x-ndjson,application/json,text/plain"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm text-gray-700 file:mr-3 file:rounded file:border file:border-gray-300 file:bg-white file:px-2 file:py-1 file:text-xs"
        />
        <p className="text-[11px] text-gray-500">
          One AnnotatedDocument JSON per line (same as server-side import). Large files may require
          raising <code className="rounded bg-gray-100 px-1">PYPEDEID_MAX_BODY_BYTES</code>.
        </p>
      </div>
      {error && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
          {error}
        </div>
      )}
      <div>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!name.trim() || !file || mutation.isPending}
          className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Upload size={16} />
          )}
          Upload and register
        </button>
      </div>
    </div>
  );
}
