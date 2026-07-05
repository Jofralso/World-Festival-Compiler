package com.festivalworld;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class LocalDeploymentRunner {
    public static void trigger(String place, String festival) throws IOException, InterruptedException {
        Path repoRoot = Path.of("/home/z3rt/festivalworld").toAbsolutePath().normalize();
        String placeSlug = place.replaceAll("[^a-zA-Z0-9._-]", "_");
        Path exportRoot = repoRoot.resolve("output").resolve(placeSlug);
        Path buildDir = exportRoot.resolve("build");
        Path serverDir = exportRoot.resolve("server_ready");

        Files.createDirectories(buildDir);
        Files.createDirectories(serverDir);

        runCommand(repoRoot, List.of(
            "python3",
            "-m",
            "cli",
            "build",
            "--map",
            repoRoot.resolve("examples/heightmap_example.png").toString(),
            "--style",
            festival,
            "--name",
            placeSlug,
            "--output",
            buildDir.toString()
        ), "FestivalWorld build");

        runCommand(repoRoot, List.of(
            "python3",
            "-m",
            "cli",
            "deploy",
            "--export-dir",
            buildDir.toString(),
            "--server-dir",
            serverDir.toString(),
            "--world-name",
            placeSlug
        ), "FestivalWorld deploy");
    }

    private static void runCommand(Path repoRoot, List<String> command, String description) throws IOException, InterruptedException {
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.directory(repoRoot.toFile());
        pb.environment().put("PYTHONPATH", repoRoot.toString());
        pb.inheritIO();
        Process process = pb.start();
        int exitCode = process.waitFor();
        if (exitCode != 0) {
            throw new IOException(description + " failed with exit code " + exitCode);
        }
    }
}
