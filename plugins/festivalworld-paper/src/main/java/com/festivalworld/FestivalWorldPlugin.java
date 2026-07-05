package com.festivalworld;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.plugin.java.JavaPlugin;

public class FestivalWorldPlugin extends JavaPlugin implements CommandExecutor {
    @Override
    public void onEnable() {
        getLogger().info("FestivalWorld plugin enabled");
        this.getCommand("festivalworld").setExecutor(this);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (args.length < 2) {
            sender.sendMessage("Usage: /festivalworld <place> <festival>");
            return true;
        }

        String place = args[0];
        String festival = String.join(" ", java.util.Arrays.copyOfRange(args, 1, args.length));
        sender.sendMessage("FestivalWorld local deployment requested for " + place + " / " + festival);
        try {
            LocalDeploymentRunner.trigger(place, festival);
            sender.sendMessage("FestivalWorld export completed locally for the selected place and festival.");
        } catch (Exception ex) {
            sender.sendMessage("FestivalWorld deployment failed: " + ex.getMessage());
            getLogger().warning(ex.getMessage());
        }
        return true;
    }
}
