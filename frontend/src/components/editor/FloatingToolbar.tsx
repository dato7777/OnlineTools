"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Pencil, Trash2, Move } from "lucide-react";

export function FloatingToolbar({
  visible,
  onEdit,
  onDelete,
  showEdit = true,
  deleteLabel = "Delete",
}: {
  visible: boolean;
  onEdit: () => void;
  onDelete: () => void;
  showEdit?: boolean;
  deleteLabel?: string;
}) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          className="glass fixed bottom-24 left-1/2 z-40 flex -translate-x-1/2 gap-1 rounded-full px-2 py-2 shadow-lg md:bottom-8"
        >
          {showEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium hover:bg-accent-muted"
            >
              <Pencil className="h-4 w-4" />
              Edit text
            </button>
          )}
          {showEdit && (
            <button
              type="button"
              className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium hover:bg-accent-muted"
              title="Drag block to move"
            >
              <Move className="h-4 w-4" />
            </button>
          )}
          <button
            type="button"
            onClick={onDelete}
            className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
          >
            <Trash2 className="h-4 w-4" />
            {deleteLabel}
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
