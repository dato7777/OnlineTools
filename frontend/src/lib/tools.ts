import { FileOutput, FilePen, Files, Image, Minimize2, type LucideIcon } from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  "file-pen": FilePen,
  files: Files,
  "minimize-2": Minimize2,
  "file-output": FileOutput,
  image: Image,
};

export function toolIcon(name: string): LucideIcon {
  return ICONS[name] ?? FilePen;
}
