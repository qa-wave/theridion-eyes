import { type LucideIcon } from "lucide-react";

interface EmptyStateAction {
  label: string;
  onClick: () => void;
}

interface Props {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: EmptyStateAction;
}

export function EmptyState({ icon: Icon, title, description, action }: Props) {
  return (
    <div className="px-3 py-6 text-center">
      {Icon && (
        <Icon size={20} className="mx-auto mb-2 text-neutral-600" />
      )}
      <p className="text-xs text-neutral-500">{title}</p>
      {description && (
        <p className="mt-1 text-[10px] text-neutral-600">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-3 rounded-md bg-neutral-800 px-3 py-1.5 text-[11px] text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-neutral-100"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
