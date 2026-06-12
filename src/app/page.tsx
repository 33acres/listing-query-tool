import { AnalyzerClient } from "@/components/AnalyzerClient";
import { loadConfig } from "@/lib/config/loadConfig";

export default function Home() {
  const config = loadConfig("dayvigo");

  return <AnalyzerClient config={config} />;
}
