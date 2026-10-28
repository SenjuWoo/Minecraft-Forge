package @PACKAGE@.testing;

import net.neoforged.fml.common.Mod;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.xml.parsers.ParserConfigurationException;
import net.minecraft.gametest.framework.GlobalTestReporter;
import net.minecraft.gametest.framework.JUnitLikeTestReporter;

// A separate development mod keeps every test/provider class out of the release JAR.
@Mod(TestMod.MODID)
public final class TestMod {
    public static final String MODID = "@MOD_ID@_tests";

    public TestMod() throws IOException, ParserConfigurationException {
        var report = System.getProperty("mcforge.gameTestReport");
        if (report != null) {
            var path = Path.of(report);
            Files.createDirectories(path.getParent());
            GlobalTestReporter.replaceWith(new JUnitLikeTestReporter(path.toFile()));
        }
    }
}
