"use client";

import React, { FormEvent, useState } from "react";
import { AddressAutocomplete } from "@/components/address-autocomplete";
import type { ZipcodeResult } from "@/lib/server/zipcode-lookup";

interface ZipcodeFormProps {
  onStateSelect: (stateCode: string) => void;
  onHouseSeatSelect: (seatId: string) => void;
  onSenateSeatSelect: (seatId: string) => void;
}

export function ZipcodeForm({ onStateSelect, onHouseSeatSelect, onSenateSeatSelect }: ZipcodeFormProps) {
  const [zipcode, setZipcode] = useState("");
  const [result, setResult] = useState<ZipcodeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!zipcode.trim()) {
      setError("Please enter a zipcode");
      return;
    }

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const params = new URLSearchParams({ zipcode: zipcode.trim() });
      const response = await fetch(`/api/v1/zipcode-lookup?${params.toString()}`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Failed to look up zipcode");
      }

      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to look up zipcode");
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  }

  function handleSelectHouseDistrict() {
    if (result?.houseDistrict && result.state) {
      onStateSelect(result.state);
      onHouseSeatSelect(result.houseDistrict);
    }
  }

  function handleSelectSenateSeat(seatId: string) {
    if (result?.state) {
      onStateSelect(result.state);
      onSenateSeatSelect(seatId);
    }
  }

  return (
    <details className="zipcode-form-container" open={isExpanded} onToggle={(e) => setIsExpanded(e.currentTarget.open)}>
      <summary className="zipcode-form-summary">
        <h3>🔍 Zipcode Lookup</h3>
        <p className="zipcode-form-hint">or enter your zipcode to auto-fill</p>
      </summary>

      <div className="zipcode-form-content">
        <form onSubmit={handleSubmit} className="zipcode-form">
          <div className="zipcode-input-group">
            <AddressAutocomplete
              value={zipcode}
              onChange={setZipcode}
              onSelect={(address, zip) => setZipcode(zip || address)}
              placeholder="Enter address or zipcode"
              disabled={isLoading}
            />
            <button type="submit" disabled={isLoading}>
              {isLoading ? "Looking up..." : "Search"}
            </button>
          </div>
        </form>

        {error && <p className="zipcode-error">{error}</p>}

        {result && (
          <div className="zipcode-results">
            <div className="zipcode-success-message">
              ✓ Zipcode {result.zipcode} found at centroid ({result.latitude?.toFixed(4)}, {result.longitude?.toFixed(4)})
            </div>
            
            <h4>Results for {result.zipcode}</h4>

            {result.normalizedAddress && (
              <p className="zipcode-address">
                <strong>Address:</strong> {result.normalizedAddress}
              </p>
            )}

            {result.state && (
              <p className="zipcode-state">
                <strong>State:</strong> {result.state}
              </p>
            )}

            {result.houseDistrict && (
              <div className="zipcode-result-section">
                <h5>House District</h5>
                <p>{result.houseDistrict}</p>
                <button
                  type="button"
                  onClick={handleSelectHouseDistrict}
                  className="zipcode-select-btn zipcode-select-house"
                >
                  Select {result.houseDistrict}
                </button>
              </div>
            )}

            {result.senateSeats.length > 0 && (
              <div className="zipcode-result-section">
                <h5>Senate Seats</h5>
                <div className="zipcode-seats-list">
                  {result.senateSeats.map((seatId) => (
                    <button
                      key={seatId}
                      type="button"
                      onClick={() => handleSelectSenateSeat(seatId)}
                      className="zipcode-select-btn zipcode-select-senate"
                    >
                      Select {seatId}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {!result.houseDistrict && result.senateSeats.length === 0 && (
              <p className="zipcode-no-results">No district or seat information found for this zipcode.</p>
            )}
          </div>
        )}
      </div>

      <style>{`
        .zipcode-form-container {
          margin-bottom: 1.5rem;
          padding: 1rem;
          border: 1px solid #e5e7eb;
          border-radius: 0.5rem;
          background-color: #f9fafb;
        }

        .zipcode-form-container[open] {
          background-color: #f3f4f6;
        }

        .zipcode-form-summary {
          cursor: pointer;
          user-select: none;
          padding: 0.5rem 0;
        }

        .zipcode-form-summary h3 {
          margin: 0;
          font-size: 1rem;
          font-weight: 600;
          display: inline;
        }

        .zipcode-form-hint {
          margin: 0.25rem 0 0 0;
          font-size: 0.875rem;
          color: #6b7280;
        }

        .zipcode-form-content {
          margin-top: 1rem;
          padding-top: 1rem;
          border-top: 1px solid #e5e7eb;
        }

        .zipcode-form {
          margin-bottom: 1rem;
        }

        .zipcode-input-group {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 1rem;
          align-items: flex-start;
        }

        .zipcode-input-group > :first-child {
          flex: 1;
          min-width: 0;
        }

        .zipcode-input-group button {
          padding: 0.5rem 1rem;
          background-color: #3b82f6;
          color: white;
          border: none;
          border-radius: 0.375rem;
          font-weight: 500;
          cursor: pointer;
        }

        .zipcode-input-group button:hover:not(:disabled) {
          background-color: #2563eb;
        }

        .zipcode-input-group button:disabled {
          background-color: #9ca3af;
          cursor: not-allowed;
        }

        .zipcode-error {
          color: #dc2626;
          font-size: 0.875rem;
          margin-bottom: 1rem;
        }

        .zipcode-results {
          background-color: white;
          padding: 1rem;
          border-radius: 0.375rem;
          border: 1px solid #e5e7eb;
        }

        .zipcode-success-message {
          background-color: #dcfce7;
          border: 1px solid #86efac;
          color: #166534;
          padding: 0.75rem;
          border-radius: 0.375rem;
          margin-bottom: 1rem;
          font-size: 0.875rem;
          font-weight: 500;
        }

        .zipcode-results h4 {
          margin: 0 0 1rem 0;
          font-size: 1rem;
          font-weight: 600;
        }

        .zipcode-address,
        .zipcode-state {
          margin: 0 0 0.75rem 0;
          font-size: 0.875rem;
          color: #374151;
        }

        .zipcode-result-section {
          margin-bottom: 1rem;
          padding: 0.75rem;
          background-color: #f9fafb;
          border-radius: 0.375rem;
          border-left: 3px solid #3b82f6;
        }

        .zipcode-result-section h5 {
          margin: 0 0 0.5rem 0;
          font-size: 0.875rem;
          font-weight: 600;
          color: #1f2937;
        }

        .zipcode-result-section p {
          margin: 0 0 0.75rem 0;
          font-size: 0.875rem;
          font-weight: 500;
          color: #374151;
        }

        .zipcode-seats-list {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .zipcode-select-btn {
          padding: 0.5rem 1rem;
          border: none;
          border-radius: 0.375rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
        }

        .zipcode-select-house {
          background-color: #10b981;
          color: white;
        }

        .zipcode-select-house:hover {
          background-color: #059669;
        }

        .zipcode-select-senate {
          background-color: #8b5cf6;
          color: white;
        }

        .zipcode-select-senate:hover {
          background-color: #7c3aed;
        }

        .zipcode-no-results {
          color: #6b7280;
          font-size: 0.875rem;
          font-style: italic;
        }
      `}</style>
    </details>
  );
}
