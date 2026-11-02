// Fixed Ghidra headless post-script. Input is parsed, never executed.
import ghidra.app.util.headless.HeadlessScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import com.google.gson.Gson;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public class ExportSummary extends HeadlessScript {
    public void run() throws Exception {
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("analysis_completed", !analysisTimeoutOccurred());
        report.put("language", currentProgram.getLanguageID().toString());
        report.put("compiler", currentProgram.getCompilerSpec().getCompilerSpecID().toString());
        report.put("function_count", currentProgram.getFunctionManager().getFunctionCount());
        List<Map<String, String>> functions = new ArrayList<>();
        FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(true);
        while (iterator.hasNext() && functions.size() < 1000) {
            Function f = iterator.next();
            Map<String, String> item = new LinkedHashMap<>();
            item.put("name", f.getName()); item.put("entry", f.getEntryPoint().toString());
            functions.add(item);
        }
        report.put("functions", functions);
        report.put("scope", "static headless analysis; no execution or maliciousness verdict");
        Files.writeString(Path.of(getScriptArgs()[0]), new Gson().toJson(report));
    }
}
