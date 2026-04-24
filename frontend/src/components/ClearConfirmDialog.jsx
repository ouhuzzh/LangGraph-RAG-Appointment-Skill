import React, { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

const ClearConfirmDialog = React.memo(function ClearConfirmDialog({ open, onConfirm, onCancel }) {
  const dialogRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      if (!dialog.open) dialog.showModal();
    } else {
      if (dialog.open) dialog.close();
    }
  }, [open]);

  function handleBackdropClick(e) {
    const rect = dialogRef.current?.getBoundingClientRect();
    if (!rect) return;
    const isOutside =
      e.clientX < rect.left ||
      e.clientX > rect.right ||
      e.clientY < rect.top ||
      e.clientY > rect.bottom;
    if (isOutside) onCancel();
  }

  return (
    <dialog ref={dialogRef} className="confirm-dialog" onClick={handleBackdropClick}>
      <div className="confirm-dialog__inner">
        <div className="confirm-dialog__icon">
          <AlertTriangle size={24} />
        </div>
        <div className="confirm-dialog__body">
          <h3>清空会话</h3>
          <p>确定要清空当前所有对话记录吗？此操作无法撤销。</p>
        </div>
        <div className="confirm-dialog__actions">
          <button type="button" className="confirm-dialog__btn--cancel" onClick={onCancel}>
            取消
          </button>
          <button type="button" className="confirm-dialog__btn--confirm" onClick={onConfirm}>
            确认清空
          </button>
        </div>
      </div>
    </dialog>
  );
});

export default ClearConfirmDialog;
