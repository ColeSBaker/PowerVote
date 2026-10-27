"use client";

import React, { useEffect, useId, useRef, useState } from "react";

interface Suggestion {
  label: string;
  zipcode: string;
}

interface AddressAutocompleteProps {
  value: string;
  onChange: (address: string) => void;
  onSelect?: (address: string, zipcode: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
}

export function AddressAutocomplete({
  value,
  onChange,
  onSelect,
  placeholder = "Enter address or zipcode",
  disabled = false,
  id,
}: AddressAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isFetching, setIsFetching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();
  const generatedId = useId();
  const inputId = id ?? generatedId;

  // Debounced fetch on value change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!value || value.length < 3) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setIsFetching(true);
      try {
        const params = new URLSearchParams({ q: value });
        const res = await fetch(`/api/v1/address-suggest?${params.toString()}`);
        if (!res.ok) return;
        const data = (await res.json()) as { suggestions?: Suggestion[] };
        setSuggestions(data.suggestions ?? []);
        setOpen((data.suggestions?.length ?? 0) > 0);
        setActiveIndex(-1);
      } catch {
        // silently degrade — user can still type freely
      } finally {
        setIsFetching(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value]);

  // Close on outside click
  useEffect(() => {
    function handlePointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  function selectSuggestion(s: Suggestion) {
    onChange(s.label);
    onSelect?.(s.label, s.zipcode);
    setSuggestions([]);
    setOpen(false);
    setActiveIndex(-1);
    inputRef.current?.focus();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[activeIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setActiveIndex(-1);
    }
  }

  return (
    <div ref={containerRef} className="aac-root">
      <div className="aac-input-wrap">
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-expanded={open}
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-opt-${activeIndex}` : undefined}
          role="combobox"
        />
        {isFetching && <span className="aac-spinner" aria-hidden="true" />}
      </div>

      {open && suggestions.length > 0 && (
        <ul
          id={listboxId}
          role="listbox"
          className="aac-list"
          onMouseLeave={() => setActiveIndex(-1)}
        >
          {suggestions.map((s, i) => (
            <li
              key={i}
              id={`${listboxId}-opt-${i}`}
              role="option"
              aria-selected={i === activeIndex}
              className={`aac-item${i === activeIndex ? " aac-item--active" : ""}`}
              onPointerDown={(e) => {
                e.preventDefault(); // prevent input blur before click fires
                selectSuggestion(s);
              }}
              onMouseEnter={() => setActiveIndex(i)}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}

      <style>{`
        .aac-root {
          position: relative;
          width: 100%;
        }

        .aac-input-wrap {
          position: relative;
          display: flex;
          align-items: center;
        }

        .aac-input-wrap input {
          width: 100%;
          padding: 0.5rem 2rem 0.5rem 0.75rem;
          border: 1px solid var(--pv-panel-border);
          border-radius: 0.375rem;
          font-size: 1rem;
          box-sizing: border-box;
          background: var(--pv-panel);
          color: var(--pv-ink);
          font-family: var(--pv-font-body);
        }

        .aac-input-wrap input::placeholder {
          color: var(--pv-muted);
        }

        .aac-input-wrap input:focus {
          outline: none;
          border-color: var(--pv-accent);
          box-shadow: 0 0 0 3px color-mix(in srgb, var(--pv-accent) 20%, transparent);
        }

        .aac-input-wrap input:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .aac-spinner {
          position: absolute;
          right: 0.6rem;
          width: 1rem;
          height: 1rem;
          border: 2px solid var(--pv-panel-border);
          border-top-color: var(--pv-accent);
          border-radius: 50%;
          animation: aac-spin 0.6s linear infinite;
          pointer-events: none;
        }

        @keyframes aac-spin {
          to { transform: rotate(360deg); }
        }

        .aac-list {
          position: absolute;
          top: calc(100% + 2px);
          left: 0;
          right: 0;
          z-index: 50;
          background: var(--pv-panel);
          border: 1px solid var(--pv-panel-border);
          border-radius: 0.375rem;
          box-shadow: var(--pv-shadow);
          list-style: none;
          margin: 0;
          padding: 0.25rem 0;
          max-height: 240px;
          overflow-y: auto;
        }

        .aac-item {
          padding: 0.5rem 0.75rem;
          font-size: 0.9rem;
          color: var(--pv-ink);
          cursor: pointer;
          line-height: 1.4;
        }

        .aac-item--active {
          background-color: var(--pv-control-bg-hover);
          color: var(--pv-accent-strong);
        }
      `}</style>
    </div>
  );
}
