import { forwardRef, type Ref } from "react";
import type { LucideIcon } from "lucide-react";

interface RailItemProps {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  active?: boolean;
  danger?: boolean;
  "data-testid"?: string;
}

export const RailItem = forwardRef<HTMLButtonElement, RailItemProps>(
  function RailItem(
    {
      icon: Icon,
      label,
      onClick,
      active = false,
      danger = false,
      "data-testid": dataTestId,
    },
    ref
  ) {
    return (
      <button
        ref={ref}
        onClick={onClick}
        data-testid={dataTestId}
        title={label}
        className={`rail-item ${active ? "rail-item-active" : ""} ${
          danger ? "rail-item-danger" : ""
        }`}
      >
        <Icon className="w-5 h-5" />
      </button>
    );
  }
);