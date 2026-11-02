// Pure selectors shared by the browser and protocol tests.
const { rosterPage } = require('./office-layout');
function worldHealth(world, now = Date.now() / 1000) {
  if (world.status === 'stopped') return 'stopped';
  return now - world.updated_at > Math.max(30, world.tick_seconds * 3 + 5) ? 'stale' : 'running';
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
  const learning = actor.learning_counts || {};
  return `${state}${task} · việc chờ ${counts.offered || 0} / vướng ${counts.blocked || 0} / xong ${counts.done || 0} · học: ${learning.episodes || 0} lượt / ${learning.proposals || 0} đề xuất / ${learning.published || 0} phát hành`;
}
module.exports = { worldHealth, rosterPage, actorActivity, actorStatus };
