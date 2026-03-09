import { useEffect, useRef } from "react";

type Props = {
    enabled?: boolean;
    isOpen: boolean;
    minWidth?: number;
    maxWidth?: number;
    onWidthChange: (width: number | null) => void;
};

export default function SidebarResizer({
    enabled = false,
    isOpen,
    minWidth = 340,
    maxWidth = 800,
    onWidthChange,
}: Props) {
    const widthRef = useRef<number | null>(null);
    const dragRef = useRef({ active: false, startX: 0, startWidth: 0 });

    // Clear inline width on mobile so CSS media queries take over;
    // restore last dragged width when coming back to desktop.
    useEffect(() => {
        if (!enabled) return;

        const breakpoint = parseInt(
            getComputedStyle(document.documentElement).getPropertyValue("--sidebar_desktop_breakpoint"),
            10
        );

        const observer = new ResizeObserver(([entry]) => {
            onWidthChange(entry.contentRect.width >= breakpoint && isOpen ? widthRef.current : null);
        });

        observer.observe(document.documentElement);
        return () => observer.disconnect();
    }, [enabled, isOpen, onWidthChange]);

    useEffect(() => {
        return () => document.body.classList.remove("gooey-sidebar-resizing");
    }, []);

    if (!enabled || !isOpen) return null;

    function handleMouseDown(event: React.MouseEvent<HTMLDivElement>) {
        event.preventDefault();
        // On the first drag widthRef is null — read current rendered width from the DOM.
        if (widthRef.current === null) {
            widthRef.current = (event.currentTarget.previousElementSibling as HTMLElement)?.offsetWidth ?? minWidth;
        }
        dragRef.current = { active: true, startX: event.clientX, startWidth: widthRef.current };
        document.body.classList.add("gooey-sidebar-resizing");

        function onMouseMove(e: MouseEvent) {
            if (!dragRef.current.active) return;
            e.preventDefault();
            const next = dragRef.current.startWidth + (e.clientX - dragRef.current.startX);
            widthRef.current = Math.min(Math.max(next, minWidth), maxWidth);
            onWidthChange(widthRef.current);
        }

        function onMouseUp() {
            dragRef.current.active = false;
            document.body.classList.remove("gooey-sidebar-resizing");
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        }

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
    }

    return <div className="gooey-sidebar-resizer" onMouseDown={handleMouseDown} />;
}