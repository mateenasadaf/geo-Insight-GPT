"use client";

import { useState } from "react";

interface VegetationResult {
  year: number;
  vegetation_percentage?: number;
  average_ndvi?: number;
  image_id?: string;
  image_date?: string;
  error?: string;
}

interface BackendResponse {
  question: string;
  plan: {
    location: string;
    analysis: string[];
    start_year: number;
    end_year: number;
  };
  results: {
    location: string;
    coordinates?: {
      latitude: number;
      longitude: number;
    };
    period: {
      start_year: number;
      end_year: number;
    };
    analyses: {
      vegetation?: VegetationResult[];
      [key: string]: unknown;
    };
  };
  report: string;
}

interface ProgressItem {
  type: string;
  message: string;
  year?: number;
  analysis?: string;
  status: "active" | "complete" | "info" | "error";
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<BackendResponse[]>([]);
  const [error, setError] = useState("");
  const [activeQuestion, setActiveQuestion] = useState("");
  const [progress, setProgress] = useState<ProgressItem[]>([]);

  const addProgress = (item: ProgressItem) => {
    setProgress((previous) => {
      // If this is a completion event, replace the corresponding active event.
      if (item.status === "complete") {
        const activeIndex = previous.findIndex(
          (existing) =>
            existing.status === "active" &&
            existing.year === item.year &&
            existing.analysis === item.analysis
        );

        if (activeIndex !== -1) {
          const updated = [...previous];
          updated[activeIndex] = item;
          return updated;
        }
      }

      // Avoid duplicate completion/status events.
      const duplicate = previous.some(
        (existing) =>
          existing.message === item.message &&
          existing.status === item.status
      );

      if (duplicate) {
        return previous;
      }

      return [...previous, item];
    });
  };

  const askGeoInsight = async (customQuestion?: string) => {
    const currentQuestion = (
      customQuestion !== undefined ? customQuestion : question
    ).trim();

    if (!currentQuestion || loading) return;

    setLoading(true);
    setError("");
    setProgress([]);
    setActiveQuestion(currentQuestion);
    setQuestion("");

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/ask/stream?question=${encodeURIComponent(
          currentQuestion
        )}`,
        {
          method: "POST",
          headers: {
            Accept: "text/event-stream",
          },
        }
      );

      if (!response.ok) {
        let message = "Backend request failed";

        try {
          const data = await response.json();
          message = data.detail || message;
        } catch {
          // Ignore JSON parsing failure.
        }

        throw new Error(message);
      }

      if (!response.body) {
        throw new Error("Streaming response is not available.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";

      const processEvent = (rawEvent: string) => {
        const lines = rawEvent.split(/\r?\n/);

        let eventType = "message";
        const dataLines: string[] = [];

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          }

          if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
          }
        }

        if (dataLines.length === 0) return;

        const rawData = dataLines.join("\n");

        let parsedData: any = rawData;

        try {
          parsedData = JSON.parse(rawData);
        } catch {
          // The backend may send plain text.
        }

        // Some SSE implementations send the event name inside the JSON.
        const actualType =
          parsedData?.event_type ||
          parsedData?.type ||
          parsedData?.event ||
          eventType;

        const message =
          parsedData?.message ||
          parsedData?.status ||
          parsedData?.text ||
          (typeof parsedData === "string" ? parsedData : "");

        const year =
          typeof parsedData?.year === "number"
            ? parsedData.year
            : undefined;

        const analysis =
          typeof parsedData?.analysis === "string"
            ? parsedData.analysis
            : undefined;

        if (
          actualType === "status" ||
          actualType === "analysis_start" ||
          actualType === "analysis_complete"
        ) {
          const status: ProgressItem["status"] =
            actualType === "analysis_complete"
              ? "complete"
              : actualType === "analysis_start"
              ? "active"
              : "info";

          addProgress({
            type: actualType,
            message:
              message ||
              (actualType === "analysis_start"
                ? "Starting geographic analysis..."
                : actualType === "analysis_complete"
                ? "Analysis step completed"
                : "Processing your geographic question..."),
            year,
            analysis,
            status,
          });

          return;
        }

        if (actualType === "error") {
          const errorMessage =
            message || "An error occurred during geographic analysis.";

          addProgress({
            type: "error",
            message: errorMessage,
            status: "error",
          });

          throw new Error(errorMessage);
        }

        if (actualType === "complete") {
          let finalResult: BackendResponse | null = null;

          // Most likely structure:
          // { event: "complete", data: {...BackendResponse} }
          if (parsedData?.data) {
            finalResult = parsedData.data;
          }

          // Alternative:
          // { event: "complete", result: {...BackendResponse} }
          if (!finalResult && parsedData?.result) {
            finalResult = parsedData.result;
          }

          // Alternative:
          // complete event directly contains BackendResponse.
          if (
            !finalResult &&
            parsedData?.question &&
            parsedData?.plan &&
            parsedData?.results
          ) {
            finalResult = parsedData;
          }

          if (finalResult) {
            setMessages((previous) => [...previous, finalResult!]);
            setActiveQuestion("");
            setProgress([]);
          }

          return;
        }

        // If the backend sends a complete BackendResponse without
        // explicitly wrapping it in a "complete" event.
        if (
          parsedData?.question &&
          parsedData?.plan &&
          parsedData?.results &&
          parsedData?.report
        ) {
          setMessages((previous) => [...previous, parsedData]);
          setActiveQuestion("");
          setProgress([]);
        }
      };

      while (true) {
        const { value, done } = await reader.read();

        if (done) {
          buffer += decoder.decode();

          const remainingEvents = buffer.split(/\r?\n\r?\n/);

          for (const event of remainingEvents) {
            if (event.trim()) {
              processEvent(event);
            }
          }

          break;
        }

        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split(/\r?\n\r?\n/);

        // Keep the last incomplete event in the buffer.
        buffer = events.pop() || "";

        for (const event of events) {
          if (event.trim()) {
            processEvent(event);
          }
        }
      }
    } catch (err) {
      console.error(err);

      setError(
        err instanceof Error
          ? err.message
          : "Unable to connect to Geo-Insight GPT."
      );

      setActiveQuestion("");
    } finally {
      setLoading(false);
    }
  };

  const newChat = () => {
    setMessages([]);
    setQuestion("");
    setError("");
    setActiveQuestion("");
    setProgress([]);
  };

  return (
    <main className="flex h-screen overflow-hidden bg-[#0b1120] text-white">

      {/* SIDEBAR */}
      <aside className="hidden w-64 flex-col border-r border-white/10 bg-[#080d18] md:flex">

        <div className="p-4">
          <button
            type="button"
            onClick={newChat}
            className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm transition hover:bg-white/[0.08]"
          >
            <span className="text-lg">＋</span>
            New analysis
          </button>
        </div>

        <div className="px-5 py-6">

          <div className="mb-4 flex items-center gap-3">

            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-500 font-bold text-slate-950 shadow-lg">
              G
            </div>

            <div>
              <p className="font-semibold">
                Geo-Insight
              </p>

              <p className="text-xs text-white/40">
                Geographic AI
              </p>
            </div>

          </div>

          <p className="text-xs leading-6 text-white/40">
            Explore geographic change using AI-powered analysis and real
            satellite imagery.
          </p>

        </div>

        <div className="mt-auto border-t border-white/10 p-5">

          <div className="space-y-2 text-xs text-white/35">
            <p>🛰 Sentinel-2 imagery</p>
            <p>🌿 NDVI analysis</p>
            <p>☁ Cloud masking</p>
            <p>🌍 Geographic intelligence</p>
          </div>

        </div>

      </aside>

      {/* MAIN */}
      <section className="relative flex min-w-0 flex-1 flex-col">

        {/* HEADER */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-white/10 bg-[#0b1120]/90 px-4 backdrop-blur md:px-7">

          <div className="flex items-center gap-3">

            <button
              type="button"
              onClick={newChat}
              className="rounded-lg px-2 py-1 text-xl hover:bg-white/10 md:hidden"
            >
              ☰
            </button>

            <div>
              <h1 className="font-semibold">
                Geo-Insight GPT
              </h1>

              <p className="text-xs text-white/35">
                Satellite-powered geographic intelligence
              </p>
            </div>

          </div>

          <div className="hidden items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/5 px-3 py-1.5 text-xs text-emerald-300 sm:flex">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                loading
                  ? "animate-pulse bg-cyan-400"
                  : "bg-emerald-400"
              }`}
            />

            {loading
              ? "Satellite analysis running"
              : "Satellite analysis ready"}
          </div>

        </header>

        {/* CHAT */}
        <div className="flex-1 overflow-y-auto">

          {messages.length === 0 && !activeQuestion ? (

            <WelcomeScreen
              loading={loading}
              askGeoInsight={askGeoInsight}
            />

          ) : (

            <div className="mx-auto max-w-5xl px-4 pb-44 pt-8 md:px-8">

              {/* COMPLETED MESSAGES */}
              {messages.map((message, index) => (

                <div key={index} className="mb-14">

                  {/* USER MESSAGE */}
                  <div className="mb-8 flex justify-end">

                    <div className="max-w-[90%] rounded-3xl rounded-br-md bg-gradient-to-r from-cyan-600/90 to-blue-600/90 px-5 py-3.5 text-sm leading-6 shadow-lg md:max-w-[70%]">
                      {message.question}
                    </div>

                  </div>

                  {/* AI RESPONSE */}
                  <div className="flex gap-3 md:gap-4">

                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-500 text-xs font-bold text-slate-950 shadow-lg">
                      G
                    </div>

                    <div className="min-w-0 flex-1">

                      {/* ANALYSIS HEADER */}
                      <AnalysisHeader
                        location={message.plan.location}
                        startYear={message.plan.start_year}
                        endYear={message.plan.end_year}
                        analysis={message.plan.analysis}
                      />

                      {/* VEGETATION DATA */}
                      <VegetationSection
                        vegetation={
                          message.results.analyses.vegetation || []
                        }
                      />

                      {/* AI REPORT */}
                      <ReportRenderer report={message.report} />

                    </div>

                  </div>

                </div>

              ))}

              {/* ACTIVE ANALYSIS */}
              {activeQuestion && (
                <div className="mb-14">

                  {/* USER QUESTION */}
                  <div className="mb-8 flex justify-end">

                    <div className="max-w-[90%] rounded-3xl rounded-br-md bg-gradient-to-r from-cyan-600/90 to-blue-600/90 px-5 py-3.5 text-sm leading-6 shadow-lg md:max-w-[70%]">
                      {activeQuestion}
                    </div>

                  </div>

                  {/* LIVE AI PROGRESS */}
                  <div className="flex gap-3 md:gap-4">

                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-500 text-xs font-bold text-slate-950 shadow-lg">
                      G
                    </div>

                    <div className="min-w-0 flex-1">
                      <AnalysisProgress
                        progress={progress}
                        loading={loading}
                      />
                    </div>

                  </div>

                </div>
              )}

            </div>

          )}

        </div>

        {/* ERROR */}
        {error && (
          <div className="absolute bottom-28 left-1/2 z-30 w-[92%] max-w-3xl -translate-x-1/2 rounded-2xl border border-red-400/20 bg-red-500/10 px-5 py-4 text-sm text-red-300 shadow-xl backdrop-blur">
            <div className="flex gap-3">
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* INPUT */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-[#0b1120] via-[#0b1120] to-transparent px-3 pb-5 pt-14 md:px-6">

          <div className="mx-auto max-w-4xl">

            <div className="flex items-end rounded-2xl border border-white/10 bg-[#151d2d]/95 px-3 py-2 shadow-2xl backdrop-blur">

              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    askGeoInsight();
                  }
                }}
                placeholder="Ask about geographic change..."
                rows={1}
                disabled={loading}
                className="max-h-40 min-h-[46px] flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-white/30 disabled:opacity-50"
              />

              <button
                type="button"
                onClick={() => askGeoInsight()}
                disabled={loading || question.trim().length === 0}
                className="ml-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-400 text-slate-950 shadow-lg transition hover:scale-105 hover:shadow-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-25 disabled:hover:scale-100"
              >
                {loading ? "⋯" : "↑"}
              </button>

            </div>

            <p className="mt-2 text-center text-[11px] text-white/25">
              Geo-Insight GPT uses real satellite observations. Results may
              vary with observation date and cloud conditions.
            </p>

          </div>

        </div>

      </section>

    </main>
  );
}


/* ================================================= */
/* WELCOME SCREEN */
/* ================================================= */

function WelcomeScreen({
  loading,
  askGeoInsight,
}: {
  loading: boolean;
  askGeoInsight: (question: string) => void;
}) {
  const suggestions = [
    {
      icon: "🌿",
      title: "Vegetation change",
      question:
        "How has vegetation changed in Mumbai from 2020 to 2026?",
    },
    {
      icon: "🌳",
      title: "Long-term change",
      question:
        "How has vegetation changed in Bengaluru from 2015 to 2025?",
    },
    {
      icon: "🏙️",
      title: "Urban environment",
      question:
        "How has vegetation changed in Delhi from 2010 to 2020?",
    },
    {
      icon: "🌊",
      title: "Coastal region",
      question:
        "How has vegetation changed in Chennai from 2018 to 2025?",
    },
  ];

  return (
    <div className="mx-auto flex min-h-full max-w-4xl flex-col justify-center px-4 pb-36 pt-10">

      <div className="mb-10 text-center">

        <div className="relative mx-auto mb-6 h-20 w-20">

          <div className="absolute inset-0 rounded-3xl bg-cyan-400/20 blur-xl" />

          <div className="relative flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-emerald-400 via-cyan-400 to-blue-500 text-3xl font-black text-slate-950 shadow-2xl">
            G
          </div>

        </div>

        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-cyan-300/70">
          Geographic Intelligence
        </p>

        <h2 className="text-4xl font-bold tracking-tight md:text-5xl">
          Explore the world
          <br />
          <span className="bg-gradient-to-r from-emerald-300 via-cyan-300 to-blue-400 bg-clip-text text-transparent">
            through satellite data.
          </span>
        </h2>

        <p className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-white/45 md:text-base">
          Ask a geographic question in natural language. Geo-Insight GPT
          identifies the location, retrieves satellite imagery, performs
          spatial analysis, and explains the results.
        </p>

      </div>

      <div className="grid gap-3 sm:grid-cols-2">

        {suggestions.map((item) => (

          <button
            type="button"
            key={item.question}
            disabled={loading}
            onClick={() => askGeoInsight(item.question)}
            className="group rounded-2xl border border-white/10 bg-white/[0.035] p-5 text-left transition hover:-translate-y-0.5 hover:border-cyan-400/20 hover:bg-white/[0.07] disabled:opacity-50"
          >

            <div className="mb-3 flex items-center justify-between">

              <span className="text-2xl">
                {item.icon}
              </span>

              <span className="text-white/20 transition group-hover:text-cyan-300">
                →
              </span>

            </div>

            <p className="mb-1 text-sm font-semibold">
              {item.title}
            </p>

            <p className="text-xs leading-5 text-white/40">
              {item.question}
            </p>

          </button>

        ))}

      </div>

    </div>
  );
}


/* ================================================= */
/* ANALYSIS PROGRESS */
/* ================================================= */

function AnalysisProgress({
  progress,
  loading,
}: {
  progress: ProgressItem[];
  loading: boolean;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 shadow-xl">

      <div className="mb-5 flex items-center gap-3">

        <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-400/10">
          <span className="absolute h-3 w-3 animate-ping rounded-full bg-cyan-400/40" />
          <span className="relative text-lg">
            🛰️
          </span>
        </div>

        <div>
          <h3 className="font-semibold">
            {loading
              ? "Analysis in progress"
              : "Analysis complete"}
          </h3>

          <p className="text-xs text-white/35">
            Processing satellite observations
          </p>
        </div>

      </div>

      {progress.length === 0 ? (

        <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3">
          <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-400" />

          <span className="text-sm text-white/55">
            Understanding your geographic question...
          </span>
        </div>

      ) : (

        <div className="space-y-2">

          {progress.map((item, index) => {

            const isActive = item.status === "active";
            const isComplete = item.status === "complete";
            const isError = item.status === "error";

            return (
              <div
                key={`${item.type}-${item.year ?? "none"}-${index}`}
                className={`flex items-center gap-3 rounded-xl px-4 py-3 transition-all ${
                  isActive
                    ? "border border-cyan-400/15 bg-cyan-400/[0.05]"
                    : isComplete
                    ? "border border-emerald-400/10 bg-emerald-400/[0.025]"
                    : isError
                    ? "border border-red-400/15 bg-red-400/[0.05]"
                    : "border border-white/5 bg-white/[0.015]"
                }`}
              >

                <span className="flex h-6 w-6 shrink-0 items-center justify-center">

                  {isComplete && (
                    <span className="text-sm text-emerald-300">
                      ✓
                    </span>
                  )}

                  {isActive && (
                    <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-cyan-400" />
                  )}

                  {isError && (
                    <span className="text-sm text-red-300">
                      !
                    </span>
                  )}

                  {!isComplete && !isActive && !isError && (
                    <span className="h-1.5 w-1.5 rounded-full bg-white/20" />
                  )}

                </span>

                <span
                  className={`text-sm ${
                    isActive
                      ? "text-cyan-200"
                      : isComplete
                      ? "text-white/55"
                      : isError
                      ? "text-red-300"
                      : "text-white/35"
                  }`}
                >
                  {item.message}
                </span>

              </div>
            );
          })}

        </div>

      )}

      {loading && (
        <div className="mt-5 flex items-center gap-2 text-[11px] text-white/25">

          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />

          <span>
            Satellite imagery • spatial analysis • geographic intelligence
          </span>

        </div>
      )}

    </div>
  );
}


/* ================================================= */
/* ANALYSIS HEADER */
/* ================================================= */

function AnalysisHeader({
  location,
  startYear,
  endYear,
  analysis,
}: {
  location: string;
  startYear: number;
  endYear: number;
  analysis: string[];
}) {
  return (
    <div className="mb-7">

      <div className="mb-4 flex flex-wrap items-center gap-2">

        <span className="rounded-full border border-cyan-400/20 bg-cyan-400/5 px-3 py-1 text-xs font-medium text-cyan-300">
          📍 {location}
        </span>

        <span className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-white/50">
          {startYear} → {endYear}
        </span>

        {analysis.map((item) => (
          <span
            key={item}
            className="rounded-full border border-emerald-400/20 bg-emerald-400/5 px-3 py-1 text-xs capitalize text-emerald-300"
          >
            🌿 {item}
          </span>
        ))}

      </div>

      <h2 className="text-xl font-semibold tracking-tight">
        Geographic Analysis
      </h2>

      <p className="mt-1 text-xs text-white/35">
        Satellite-derived observations for {location}
      </p>

    </div>
  );
}


/* ================================================= */
/* VEGETATION SECTION */
/* ================================================= */

function VegetationSection({
  vegetation,
}: {
  vegetation: VegetationResult[];
}) {
  const valid = vegetation.filter(
    (item) =>
      item.vegetation_percentage !== undefined &&
      item.average_ndvi !== undefined
  );

  if (valid.length === 0) {
    return null;
  }

  const first = valid[0];
  const last = valid[valid.length - 1];

  const vegetationChange =
    last.vegetation_percentage! -
    first.vegetation_percentage!;

  const ndviChange =
    last.average_ndvi! -
    first.average_ndvi!;

  const highestVegetation = valid.reduce((a, b) =>
    a.vegetation_percentage! > b.vegetation_percentage! ? a : b
  );

  const lowestVegetation = valid.reduce((a, b) =>
    a.vegetation_percentage! < b.vegetation_percentage! ? a : b
  );

  return (
    <div className="space-y-6">

      <div className="flex items-center gap-3">

        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-400/10">
          🌿
        </div>

        <div>
          <h3 className="font-semibold">
            Vegetation Analysis
          </h3>

          <p className="text-xs text-white/35">
            Derived from Sentinel-2 NDVI analysis
          </p>
        </div>

      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">

        <MetricCard
          label="Latest vegetation"
          value={`${last.vegetation_percentage!.toFixed(2)}%`}
          subtitle={`${last.year}`}
          icon="🌱"
        />

        <MetricCard
          label="Latest NDVI"
          value={last.average_ndvi!.toFixed(3)}
          subtitle={`${last.year}`}
          icon="📡"
        />

        <MetricCard
          label="Highest coverage"
          value={`${highestVegetation.vegetation_percentage!.toFixed(2)}%`}
          subtitle={`${highestVegetation.year}`}
          icon="📈"
        />

        <MetricCard
          label="Overall change"
          value={`${vegetationChange >= 0 ? "+" : ""}${vegetationChange.toFixed(2)} pp`}
          subtitle={`${first.year} → ${last.year}`}
          icon={vegetationChange >= 0 ? "↗" : "↘"}
          negative={vegetationChange < 0}
        />

      </div>

      <div className="grid gap-5 xl:grid-cols-2">

        <ChartCard
          title="Vegetation Coverage"
          subtitle="Percentage of valid analyzed pixels classified as vegetation"
        >
          <LineChart
            data={valid.map((item) => ({
              year: item.year,
              value: item.vegetation_percentage!,
            }))}
            suffix="%"
            decimals={2}
          />
        </ChartCard>

        <ChartCard
          title="Average NDVI"
          subtitle="Normalized Difference Vegetation Index"
        >
          <LineChart
            data={valid.map((item) => ({
              year: item.year,
              value: item.average_ndvi!,
            }))}
            suffix=""
            decimals={3}
          />
        </ChartCard>

      </div>

      <div className="rounded-2xl border border-cyan-400/10 bg-gradient-to-r from-cyan-400/[0.06] to-emerald-400/[0.04] p-5">

        <div className="flex gap-3">

          <div className="text-xl">
            💡
          </div>

          <div>

            <p className="mb-1 text-sm font-semibold">
              Quick insight
            </p>

            <p className="text-sm leading-6 text-white/55">
              Vegetation coverage changed by{" "}
              <span className="font-semibold text-white">
                {vegetationChange >= 0 ? "+" : ""}
                {vegetationChange.toFixed(2)} percentage points
              </span>{" "}
              between {first.year} and {last.year}. Average NDVI changed by{" "}
              <span className="font-semibold text-white">
                {ndviChange >= 0 ? "+" : ""}
                {ndviChange.toFixed(3)}
              </span>.
            </p>

          </div>

        </div>

      </div>

      <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02]">

        <div className="border-b border-white/10 px-5 py-4">

          <h3 className="text-sm font-semibold">
            Year-by-Year Measurements
          </h3>

          <p className="mt-1 text-xs text-white/35">
            Actual observations returned by the satellite analysis engine
          </p>

        </div>

        <div className="overflow-x-auto">

          <table className="w-full min-w-[600px] text-left text-sm">

            <thead className="bg-white/[0.03] text-xs text-white/35">
              <tr>
                <th className="px-5 py-3">Year</th>
                <th className="px-5 py-3">Vegetation</th>
                <th className="px-5 py-3">NDVI</th>
                <th className="px-5 py-3">Observation</th>
              </tr>
            </thead>

            <tbody>

              {valid.map((item) => (

                <tr
                  key={item.year}
                  className="border-t border-white/5 transition hover:bg-white/[0.025]"
                >

                  <td className="px-5 py-3.5 font-semibold">
                    {item.year}
                  </td>

                  <td className="px-5 py-3.5 text-emerald-300">
                    {item.vegetation_percentage!.toFixed(2)}%
                  </td>

                  <td className="px-5 py-3.5 text-cyan-300">
                    {item.average_ndvi!.toFixed(3)}
                  </td>

                  <td className="px-5 py-3.5 text-white/40">
                    {item.image_date
                      ? new Date(item.image_date).toLocaleDateString()
                      : "N/A"}
                  </td>

                </tr>

              ))}

            </tbody>

          </table>

        </div>

      </div>

      <p className="text-xs text-white/25">
        Lowest vegetation coverage:{" "}
        {lowestVegetation.vegetation_percentage!.toFixed(2)}%
        {" "}in {lowestVegetation.year}.
      </p>

    </div>
  );
}


/* ================================================= */
/* CHART CARD */
/* ================================================= */

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5">

      <div className="mb-5">

        <h3 className="text-sm font-semibold">
          {title}
        </h3>

        <p className="mt-1 text-xs text-white/35">
          {subtitle}
        </p>

      </div>

      {children}

    </div>
  );
}


/* ================================================= */
/* SVG LINE CHART */
/* ================================================= */

function LineChart({
  data,
  suffix,
  decimals,
}: {
  data: { year: number; value: number }[];
  suffix: string;
  decimals: number;
}) {
  if (data.length < 2) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-white/30">
        Not enough yearly data for a trend chart.
      </div>
    );
  }

  const width = 700;
  const height = 300;

  const padding = {
    top: 25,
    right: 25,
    bottom: 45,
    left: 50,
  };

  const values = data.map((item) => item.value);

  let min = Math.min(...values);
  let max = Math.max(...values);

  if (min === max) {
    min -= 1;
    max += 1;
  }

  const range = max - min;

  const chartWidth =
    width - padding.left - padding.right;

  const chartHeight =
    height - padding.top - padding.bottom;

  const points = data.map((item, index) => {

    const x =
      padding.left +
      (index / (data.length - 1)) * chartWidth;

    const y =
      padding.top +
      ((max - item.value) / range) * chartHeight;

    return {
      ...item,
      x,
      y,
    };
  });

  const path = points
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`
    )
    .join(" ");

  const areaPath = `
    ${path}
    L ${points[points.length - 1].x} ${height - padding.bottom}
    L ${points[0].x} ${height - padding.bottom}
    Z
  `;

  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="w-full overflow-hidden">

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
      >

        {gridLines.map((fraction) => {

          const y =
            padding.top + fraction * chartHeight;

          const value =
            max - fraction * range;

          return (
            <g key={fraction}>

              <line
                x1={padding.left}
                x2={width - padding.right}
                y1={y}
                y2={y}
                stroke="rgba(255,255,255,0.07)"
                strokeWidth="1"
              />

              <text
                x={padding.left - 8}
                y={y + 4}
                textAnchor="end"
                fill="rgba(255,255,255,0.3)"
                fontSize="11"
              >
                {value.toFixed(decimals)}
                {suffix}
              </text>

            </g>
          );
        })}

        <path
          d={areaPath}
          fill="rgba(34,211,238,0.07)"
        />

        <path
          d={path}
          fill="none"
          stroke="#22d3ee"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {points.map((point) => (

          <g key={point.year}>

            <circle
              cx={point.x}
              cy={point.y}
              r="5"
              fill="#0b1120"
              stroke="#34d399"
              strokeWidth="2"
            />

            <text
              x={point.x}
              y={height - 17}
              textAnchor="middle"
              fill="rgba(255,255,255,0.4)"
              fontSize="11"
            >
              {point.year}
            </text>

          </g>

        ))}

      </svg>

    </div>
  );
}


/* ================================================= */
/* REPORT RENDERER */
/* ================================================= */

function ReportRenderer({
  report,
}: {
  report: string;
}) {
  const sections = parseReport(report);

  return (
    <div className="mt-10">

      <div className="mb-6 flex items-center gap-3">

        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-400/10">
          ✦
        </div>

        <div>
          <h3 className="font-semibold">
            AI Geographic Report
          </h3>

          <p className="text-xs text-white/35">
            Interpretation of the measured satellite results
          </p>
        </div>

      </div>

      <div className="space-y-5">

        {sections.map((section, index) => (

          <ReportSection
            key={index}
            title={section.title}
            content={section.content}
            index={index}
          />

        ))}

      </div>

    </div>
  );
}


/* ================================================= */
/* REPORT PARSER */
/* ================================================= */

function parseReport(report: string) {

  const lines = report.split("\n");

  const sections: {
    title: string;
    content: string;
  }[] = [];

  let currentTitle = "Analysis";
  let currentContent: string[] = [];

  const pushCurrent = () => {

    const content = currentContent.join("\n").trim();

    if (content) {
      sections.push({
        title: currentTitle,
        content,
      });
    }

  };

  for (const line of lines) {

    if (line.trim().startsWith("## ")) {

      pushCurrent();

      currentTitle = line
        .replace(/^##\s*/, "")
        .trim();

      currentContent = [];

    } else {

      currentContent.push(line);

    }

  }

  pushCurrent();

  return sections;
}


/* ================================================= */
/* REPORT SECTION */
/* ================================================= */

function ReportSection({
  title,
  content,
  index,
}: {
  title: string;
  content: string;
  index: number;
}) {
  const icon =
    title.toLowerCase().includes("summary")
      ? "✦"
      : title.toLowerCase().includes("year")
      ? "📅"
      : title.toLowerCase().includes("trend")
      ? "📈"
      : title.toLowerCase().includes("important")
      ? "⚠"
      : "◈";

  return (
    <section className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025]">

      <div className="flex items-center gap-3 border-b border-white/10 bg-white/[0.025] px-5 py-4">

        <div
          className={`flex h-9 w-9 items-center justify-center rounded-xl ${
            index === 0
              ? "bg-cyan-400/10 text-cyan-300"
              : index === 1
              ? "bg-emerald-400/10 text-emerald-300"
              : index === 2
              ? "bg-blue-400/10 text-blue-300"
              : "bg-amber-400/10 text-amber-300"
          }`}
        >
          {icon}
        </div>

        <h3 className="text-sm font-semibold md:text-base">
          {title}
        </h3>

      </div>

      <div className="px-5 py-5 text-sm leading-7 text-white/65">
        <FormattedReportText content={content} />
      </div>

    </section>
  );
}


/* ================================================= */
/* FORMATTED REPORT TEXT */
/* ================================================= */

function FormattedReportText({
  content,
}: {
  content: string;
}) {
  const lines = content.split("\n");

  return (
    <div className="space-y-2">

      {lines.map((line, index) => {

        const trimmed = line.trim();

        if (!trimmed) {
          return <div key={index} className="h-1" />;
        }

        if (trimmed.startsWith("* ")) {

          return (
            <div
              key={index}
              className="flex gap-3 rounded-lg px-2 py-1.5 transition hover:bg-white/[0.025]"
            >
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" />

              <span>
                {formatBoldText(trimmed.substring(2))}
              </span>
            </div>
          );
        }

        if (/^\d+\.\s/.test(trimmed)) {

          const match = trimmed.match(/^(\d+\.)\s(.*)$/);

          return (
            <div
              key={index}
              className="flex gap-3 rounded-lg px-2 py-1.5"
            >

              <span className="font-semibold text-cyan-300">
                {match?.[1]}
              </span>

              <span>
                {formatBoldText(match?.[2] || "")}
              </span>

            </div>
          );
        }

        return (
          <p key={index}>
            {formatBoldText(trimmed)}
          </p>
        );
      })}

    </div>
  );
}


/* ================================================= */
/* BOLD TEXT */
/* ================================================= */

function formatBoldText(text: string) {

  const parts = text.split(/(\*\*.*?\*\*)/g);

  return parts.map((part, index) => {

    if (part.startsWith("**") && part.endsWith("**")) {

      return (
        <strong
          key={index}
          className="font-semibold text-white"
        >
          {part.slice(2, -2)}
        </strong>
      );
    }

    return <span key={index}>{part}</span>;
  });
}


/* ================================================= */
/* METRIC CARD */
/* ================================================= */

function MetricCard({
  label,
  value,
  subtitle,
  icon,
  negative,
}: {
  label: string;
  value: string;
  subtitle: string;
  icon: string;
  negative?: boolean;
}) {
  return (
    <div className="group rounded-2xl border border-white/10 bg-white/[0.025] p-4 transition hover:-translate-y-0.5 hover:border-white/15 hover:bg-white/[0.045]">

      <div className="mb-3 flex items-center justify-between">

        <p className="text-xs text-white/35">
          {label}
        </p>

        <span className="text-sm opacity-60">
          {icon}
        </span>

      </div>

      <p
        className={`text-2xl font-bold tracking-tight ${
          negative
            ? "text-rose-300"
            : "bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent"
        }`}
      >
        {value}
      </p>

      <p className="mt-1 text-[11px] text-white/25">
        {subtitle}
      </p>

    </div>
  );
}