package @PACKAGE@.@NAME@.home;

import com.mojang.serialization.Codec;
import com.mojang.serialization.MapCodec;
import com.mojang.serialization.codecs.RecordCodecBuilder;
import java.util.Optional;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.level.NoiseColumn;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.structure.Structure;
import net.minecraft.world.level.levelgen.structure.StructureType;
import net.minecraft.world.level.levelgen.structure.templatesystem.StructureTemplate;
import net.minecraft.world.level.material.Fluid;

/**
 * A single-template structure anchored to a natural fluid surface: lava lakes and seas, the Nether lava sea, water.
 * Structure type {@code @MODID@:@NAME@_home} (toolkit: kit PROJECT home --mob @NAME@). Yours to edit.
 *
 * <p>Why a custom type: lake features generate after structures and cannot be queried during placement, but the
 * chunk generator's base column already contains aquifer fluids and seas. This samples columns of the candidate
 * chunk, needs {@code fluid} with at least {@code air_above} open blocks over it between {@code min_y} and
 * {@code max_y}, and puts the template floor at the fluid surface + 1 + {@code floor_offset}. For a structure that
 * simply sits on the surface, use a {@code minecraft:jigsaw} single piece instead (no Java needed).
 *
 * <pre>{"type": "@MODID@:@NAME@_home", "biomes": "#@MODID@:has_structure/NAME", "step": "underground_structures",
 *  "spawn_overrides": {}, "terrain_adaptation": "none", "template": "@MODID@:NAME",
 *  "fluid": "minecraft:lava", "min_y": -63, "max_y": -1, "air_above": 6, "floor_offset": -1}</pre>
 * Overworld caves: y -63..-1. Nether lava sea: y 24..40 with step surface_structures.
 */
public class @PASCAL@HomeStructure extends Structure {
    public static final MapCodec<@PASCAL@HomeStructure> CODEC = RecordCodecBuilder.mapCodec(i -> i.group(
            settingsCodec(i),
            ResourceLocation.CODEC.fieldOf("template").forGetter(s -> s.template),
            ResourceLocation.CODEC.optionalFieldOf("fluid", ResourceLocation.withDefaultNamespace("lava")).forGetter(s -> s.fluid),
            Codec.INT.fieldOf("min_y").forGetter(s -> s.minY),
            Codec.INT.fieldOf("max_y").forGetter(s -> s.maxY),
            Codec.INT.optionalFieldOf("air_above", 6).forGetter(s -> s.airAbove),
            Codec.INT.optionalFieldOf("floor_offset", 0).forGetter(s -> s.floorOffset)
    ).apply(i, @PASCAL@HomeStructure::new));

    final ResourceLocation template;
    final ResourceLocation fluid;
    final int minY, maxY, airAbove, floorOffset;

    public @PASCAL@HomeStructure(StructureSettings settings, ResourceLocation template, ResourceLocation fluid, int minY, int maxY,
                              int airAbove, int floorOffset) {
        super(settings);
        this.template = template;
        this.fluid = fluid;
        this.minY = minY;
        this.maxY = maxY;
        this.airAbove = airAbove;
        this.floorOffset = floorOffset;
    }

    /** The fluid surface y of a column (fluid with {@code airAbove} open blocks over it), or Integer.MIN_VALUE. Public for tests. */
    public static int fluidSurface(NoiseColumn column, Fluid fluid, int minY, int maxY, int airAbove) {
        for (int y = minY; y <= maxY; y++) {
            BlockState state = column.getBlock(y);
            if (!state.getFluidState().is(fluid) || column.getBlock(y + 1).getFluidState().is(fluid)) {
                continue;
            }
            boolean open = true;
            for (int k = 1; k <= airAbove && open; k++) {
                open = column.getBlock(y + k).isAir();
            }
            if (open) {
                return y;
            }
        }
        return Integer.MIN_VALUE;
    }

    @Override
    protected Optional<GenerationStub> findGenerationPoint(GenerationContext context) {
        Fluid wanted = BuiltInRegistries.FLUID.get(fluid);
        int bestY = Integer.MIN_VALUE, bestX = 0, bestZ = 0;
        // 16 columns per chunk: a base column costs a few milliseconds, and this runs for every candidate chunk
        for (int dx = 2; dx < 16; dx += 4) {
            for (int dz = 2; dz < 16; dz += 4) {
                int x = context.chunkPos().getBlockX(dx), z = context.chunkPos().getBlockZ(dz);
                NoiseColumn column = context.chunkGenerator().getBaseColumn(x, z, context.heightAccessor(), context.randomState());
                int y = fluidSurface(column, wanted, minY, maxY, airAbove);
                if (y != Integer.MIN_VALUE && y > bestY) {
                    bestY = y;
                    bestX = x;
                    bestZ = z;
                }
            }
        }
        if (bestY == Integer.MIN_VALUE) {
            return Optional.empty();
        }
        Rotation rotation = Rotation.getRandom(context.random());
        StructureTemplate loaded = context.structureTemplateManager().getOrCreate(template);
        BlockPos pivot = new BlockPos(loaded.getSize().getX() / 2, 0, loaded.getSize().getZ() / 2);
        BlockPos origin = new BlockPos(bestX - pivot.getX(), bestY + 1 + floorOffset, bestZ - pivot.getZ());
        return Optional.of(new GenerationStub(new BlockPos(bestX, bestY + 1, bestZ), builder ->
                builder.addPiece(new @PASCAL@HomePiece(context.structureTemplateManager(), template, origin, rotation, pivot))));
    }

    @Override
    public StructureType<?> type() {
        return @PASCAL@HomeContent.STRUCTURE_TYPE.get();
    }
}
