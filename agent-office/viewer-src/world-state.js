// Pure selectors shared by the browser and protocol tests.
function worldHealth(world, now = Date.now() / 1000) {
  if (world.status === 'stopped') return 'stopped';
  return now - world.updated_at > Math.max(30, world.tick_seconds * 3 + 5) ? 'stale' : 'running';
}
function rosterPage(world, team = 'all', page = 0) {
  const list = world.actors.filter(a => team === 'all' || a.team === team);
  const pages = Math.max(1, Math.ceil(list.length / 20));
  const index = Math.max(0, Math.min(page, pages - 1));
  return { items: list.slice(index * 20, index * 20 + 20), page: index, pages, count: list.length };
}
function actorActivity(world, actor, now) {
  if (worldHealth(world, now) !== 'running') return 'idle';
  if (actor.control_status && actor.control_status !== 'ACTIVE') return 'idle';
  if (actor.activity === 'planning') return 'think';
  return actor.last_tick === world.tick ? 'tool' : 'idle';
}
function actorStatus(actor) {
  const state = actor.control_status === 'DONE' ? 'Đã hoàn tất'
    : actor.control_status === 'WAITING' ? `Chờ tới tick ${actor.wake_tick}` : 'Sẵn sàng';
  const task = actor.active_task ? ` · ${actor.active_specialty} · ${actor.active_task}` : '';
  const counts = actor.task_counts || {};
  return `${state}${task} · việc chờ ${counts.offered || 0} / vướng ${counts.blocked || 0} / xong ${counts.done || 0}`;
}
module.exports = { worldHealth, rosterPage, actorActivity, actorStatus };
