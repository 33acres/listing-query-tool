"use client";

import { useCallback, useRef, useState } from "react";

interface Props {
  onFile: (buffer: ArrayBuffer, fileName: string) => void;
  isLoading: boolean;
}

export function CsvUploader({ onFile, isLoading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFile = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        if (e.target?.result instanceof ArrayBuffer) {
          onFile(e.target.result, file.name);
        }
      };
      reader.readAsArrayBuffer(file);
    },
    [onFile]
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
        isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400"
      }`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={handleChange}
      />
      {isLoading ? (
        <p className="text-gray-500">解析中...</p>
      ) : (
        <>
          <p className="text-lg font-medium text-gray-700 mb-1">
            Google広告 検索語句レポートCSVをアップロード
          </p>
          <p className="text-sm text-gray-400">
            クリックまたはドラッグ&ドロップ（UTF-8 / Shift-JIS / UTF-16LE対応）
          </p>
        </>
      )}
    </div>
  );
}
