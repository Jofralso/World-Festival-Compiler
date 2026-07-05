package com.festivalworld;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class LocalDeploymentRunner {
    public static void trigger(String place, String festival) throws IOException, InterruptedException {
        Path repoRoot = Path.of("/home/z3rt/festivalworld").toAbsolutePath();
        Path exportDir = repoRoot.resolve("output").resolve(place.replaceAll("[^a-zA-Z0-9._-]", "_")).resolve("server_ready");
        Files.createDirectories(exportDir);

        List<String> command = new ArrayList<>();
        command.add("python3");
        command.add("-m");
        command.add("festivalworld.cli");
        command.add("build");
        command.add("--map");
        command.add(repoRoot.resolve("examples/heightmap_example.png").toString());
        command.add("--style");
        command.add(festival);
        command.add("--name");
        command.add(place.replaceAll("[^a-zA-Z0-9._-]", "_"));
        command.add("--output");
        command.add(exportDir.toString());

        ProcessBuilder pb = new ProcessBuilder(command);
        pb.directory(repoRoot.toFile());
        pb.environment().put("PYTHONPATH", repoRoot.toString());
        pb.inheritIO();
        Process process = pb.start();
        int exitCode = process.waitFor();
        if (exitCode != 0) {
            throw new IOException("FestivalWorld build failed with exit code " + exitCode);
        }
    }
}
