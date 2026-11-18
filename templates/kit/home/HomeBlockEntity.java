package @PACKAGE@.@NAME@.home;

import @PACKAGE@.@NAME@.@PASCAL@Content;
import java.util.List;
import java.util.UUID;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.MobSpawnType;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;

/**
 * Forms the mob on the first server tick, adopts one that already lives here, and re-forms it after it is gone.
 * The mob remembers its home in its persistent data ({@link #HOME_KEY}), so "who lives here" survives reloads
 * without a field in the entity class. Read it from the entity for leashing, schedules and returning home:
 * {@code BlockPos.of(entity.getPersistentData().getLong(HOME_KEY))}.
 */
public class @PASCAL@HomeBlockEntity extends BlockEntity {
    public static final String HOME_KEY = "@MODID@:@NAME@_home";
    /** Ticks until a missing resident is formed again (one game day). Call {@link #residentLeft} for a shorter wait. */
    public static final int RESPAWN_TICKS = 24000;
    private UUID resident;
    private int respawnIn;
    private boolean formed;

    public @PASCAL@HomeBlockEntity(BlockPos pos, BlockState state) {
        super(@PASCAL@HomeContent.BLOCK_ENTITY.get(), pos, state);
    }

    public static void serverTick(Level level, BlockPos pos, BlockState state, @PASCAL@HomeBlockEntity home) {
        if (!(level instanceof ServerLevel server)) {
            return;
        }
        if (home.respawnIn > 0) {
            if (--home.respawnIn == 0) {
                home.form(server);
            } else if (home.respawnIn % 100 == 0) {
                home.setChanged();
            }
            return;
        }
        if (!home.formed) {
            home.form(server);
            return;
        }
        // Only decide "gone" where entities really tick: an unloaded resident is not a missing one.
        if (level.getGameTime() % 40 == 0 && home.resident != null && server.getEntity(home.resident) == null
                && server.isPositionEntityTicking(pos) && home.residents(server).isEmpty()) {
            home.resident = null;
            home.respawnIn = RESPAWN_TICKS;
            home.setChanged();
        }
    }

    private List<Mob> residents(ServerLevel level) {
        long key = worldPosition.asLong();
        return level.getEntitiesOfClass(Mob.class, new AABB(worldPosition).inflate(48),
                mob -> mob.getType() == @PASCAL@Content.TYPE.get() && mob.getPersistentData().getLong(HOME_KEY) == key);
    }

    /** Tell the home its resident left on purpose (a scripted exit, a defeat that is not a death): re-form after {@code ticks}. */
    public void residentLeft(UUID who, int ticks) {
        if (who.equals(resident)) {
            resident = null;
            respawnIn = Math.max(20, ticks);
            setChanged();
        }
    }

    private void form(ServerLevel level) {
        List<Mob> existing = residents(level);
        if (!existing.isEmpty()) {
            resident = existing.get(0).getUUID();
            formed = true;
            setChanged();
            return;
        }
        Mob mob = @PASCAL@Content.TYPE.get().create(level);
        if (mob == null) {
            return;
        }
        BlockPos spot = findSpot(level, worldPosition);
        mob.moveTo(spot.getX() + 0.5, spot.getY(), spot.getZ() + 0.5, level.random.nextFloat() * 360f, 0f);
        mob.getPersistentData().putLong(HOME_KEY, worldPosition.asLong());
        mob.finalizeSpawn(level, level.getCurrentDifficultyAt(spot), MobSpawnType.STRUCTURE, null);
        mob.setPersistenceRequired();
        level.addFreshEntityWithPassengers(mob);
        resident = mob.getUUID();
        formed = true;
        setChanged();
    }

    /** A free, dry standing place with a sturdy floor near the block. */
    private static BlockPos findSpot(ServerLevel level, BlockPos near) {
        for (int r = 1; r <= 4; r++) {
            for (int dx = -r; dx <= r; dx++) {
                for (int dz = -r; dz <= r; dz++) {
                    for (int dy = -2; dy <= 2; dy++) {
                        BlockPos p = near.offset(dx, dy, dz);
                        if (level.getBlockState(p.below()).isFaceSturdy(level, p.below(), Direction.UP) && level.getFluidState(p).isEmpty()
                                && level.noCollision(@PASCAL@Content.TYPE.get().getSpawnAABB(p.getX() + 0.5, p.getY(), p.getZ() + 0.5))) {
                            return p;
                        }
                    }
                }
            }
        }
        return near.above();
    }

    @Override
    protected void saveAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.saveAdditional(tag, registries);
        if (resident != null) {
            tag.putUUID("Resident", resident);
        }
        tag.putInt("RespawnIn", respawnIn);
        tag.putBoolean("Formed", formed);
    }

    @Override
    protected void loadAdditional(CompoundTag tag, HolderLookup.Provider registries) {
        super.loadAdditional(tag, registries);
        resident = tag.hasUUID("Resident") ? tag.getUUID("Resident") : null;
        respawnIn = tag.getInt("RespawnIn");
        formed = tag.getBoolean("Formed");
    }
}
