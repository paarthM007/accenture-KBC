"use client";

import { useState } from "react";
import { analyzeUpload, validate, type ApiResponse, type FormMetadata, type ValidateResponse } from "@/lib/api";
import { SCENARIOS, type ScenarioName } from "@/lib/scenarios";
import { InputForm } from "@/components/InputForm";
import { MappingConfirmation } from "@/components/MappingConfirmation";
import { ResultsView } from "@/components/ResultsView";
import { ScenarioSwitcher } from "@/components/ScenarioSwitcher";

type Step = "form" | "mapping" | "results";

export default function Home() {
  const [step, setStep] = useState<Step>("form");
  const [file, setFile] = useState<File | null>(null);
  const [metadata, setMetadata] = useState<FormMetadata | null>(null);
  const [validateResponse, setValidateResponse] = useState<ValidateResponse | null>(null);
  const [apiResponse, setApiResponse] = useState<ApiResponse | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const reset = () => {
    setStep("form");
    setFile(null);
    setMetadata(null);
    setValidateResponse(null);
    setApiResponse(null);
    setErrorMessage(null);
  };

  const handleFormSubmit = async (submittedFile: File, submittedMetadata: FormMetadata) => {
    setErrorMessage(null);
    setIsValidating(true);
    try {
      const response = await validate(submittedFile, submittedMetadata);
      setFile(submittedFile);
      setMetadata(submittedMetadata);
      setValidateResponse(response);
      setStep("mapping");
    } catch {
      setErrorMessage("Could not reach the analysis server. Is the API running?");
    } finally {
      setIsValidating(false);
    }
  };

  const handleMappingConfirm = async (overrides: Record<string, string>) => {
    if (!file || !metadata) return;
    setErrorMessage(null);
    setIsAnalyzing(true);
    try {
      const response = await analyzeUpload(file, metadata, overrides);
      setApiResponse(response);
      setStep("results");
    } catch {
      setErrorMessage("Could not reach the analysis server. Is the API running?");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleScenarioSelect = (scenario: ScenarioName) => {
    setApiResponse(SCENARIOS[scenario]);
    setStep("results");
  };

  return (
    <main className="flex-1 px-4 sm:px-6">
      {errorMessage && (
        <div className="mx-auto mt-6 max-w-prose rounded-sm border border-flag/40 bg-flag/[0.06] p-3 text-sm text-ink">
          {errorMessage}
        </div>
      )}

      {step === "form" && <InputForm onSubmit={handleFormSubmit} isSubmitting={isValidating} />}

      {step === "mapping" && validateResponse && (
        <MappingConfirmation
          validateResponse={validateResponse}
          onConfirm={handleMappingConfirm}
          onBack={reset}
          isSubmitting={isAnalyzing}
        />
      )}

      {step === "results" && apiResponse && <ResultsView response={apiResponse} onReset={reset} />}

      <ScenarioSwitcher onSelect={handleScenarioSelect} onLiveDemo={reset} />
    </main>
  );
}
