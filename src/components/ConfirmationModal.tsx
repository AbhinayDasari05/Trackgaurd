import React from 'react';
import { CheckCircle2, AlertTriangle } from 'lucide-react';

interface Props {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'success' | 'danger';
}

export const ConfirmationModal: React.FC<Props> = ({
  isOpen,
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  variant = 'success'
}) => {
  if (!isOpen) return null;

  const isSuccess = variant === 'success';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md bg-[#0d1527] border border-[#1f2d4d] rounded-2xl p-6 shadow-2xl space-y-5">
        <div className="flex items-center gap-3">
          <div className={`p-3 rounded-xl ${isSuccess ? 'bg-cyan-950/80 text-cyan-400 border border-cyan-700/50' : 'bg-red-950/80 text-red-400 border border-red-700/50'}`}>
            {isSuccess ? <CheckCircle2 className="w-6 h-6" /> : <AlertTriangle className="w-6 h-6" />}
          </div>
          <h3 className="text-xl font-bold text-white tracking-wide">{title}</h3>
        </div>

        <p className="text-slate-300 text-sm leading-relaxed">{message}</p>

        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium rounded-lg text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-700 transition-colors cursor-pointer"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`px-5 py-2 text-sm font-semibold rounded-lg text-black transition-all cursor-pointer shadow-lg ${
              isSuccess
                ? 'bg-cyan-400 hover:bg-cyan-300 shadow-cyan-500/20'
                : 'bg-red-500 hover:bg-red-400 shadow-red-500/20 text-white'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
