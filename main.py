# Based on Roaming Ralph sample from the Panda3D codebase

import sys

import pman.shim
import eventmapper
import simplepbr

from direct.showbase.ShowBase import ShowBase
from direct.actor.Actor import Actor
import panda3d.core as p3d

p3d.load_prc_file(
    p3d.Filename.expand_from('$MAIN_DIR/settings.prc')
)

p3d.load_prc_file(
    p3d.Filename.expand_from('$MAIN_DIR/user.prc')
)


class CharacterController:
    MOVE_SPEED = 20
    TURN_SPEED = 300

    def __init__(self, target, traverser):
        self.target = target

        # Use a pusher for obstacle avoidance
        self._char_col = p3d.CollisionNode('obstacle_collider')
        self._char_col.add_solid(p3d.CollisionSphere(center=(0, 0, 2), radius=1.5))
        self._char_col.add_solid(p3d.CollisionSphere(center=(0, -0.25, 4), radius=1.5))
        self._char_col.set_from_collide_mask(p3d.CollideMask.bit(0))
        self._char_col.set_into_collide_mask(p3d.CollideMask.allOff())
        self._char_col_np = target.attach_new_node(self._char_col)
        self._char_pusher = p3d.CollisionHandlerPusher()
        self._char_pusher.horizontal = True

        self._char_pusher.add_collider(self._char_col_np, target)
        traverser.add_collider(self._char_col_np, self._char_pusher)

        # Use a ray to keep the character on the ground
        self._char_ground_ray = p3d.CollisionRay()
        self._char_ground_ray.set_origin(0, 0, 9)
        self._char_ground_ray.set_direction(0, 0, -1)
        self._char_ground_col = p3d.CollisionNode('ground_ray')
        self._char_ground_col.add_solid(self._char_ground_ray)
        self._char_ground_col.set_from_collide_mask(p3d.CollideMask.bit(0))
        self._char_ground_col.set_into_collide_mask(p3d.CollideMask.allOff())
        self._char_ground_col_np = target.attach_new_node(self._char_ground_col)
        self._char_ground_handler = p3d.CollisionHandlerQueue()
        traverser.add_collider(self._char_ground_col_np, self._char_ground_handler)

        # Direction to move in
        self.move_delta = p3d.LVector2(0, 0)
        self._prev_move_delta = p3d.LVector2(0, 0)

        # Direction to turn in
        self.turn_delta = 0
        self._prev_turn_delta = 0

    def update(self):
        dt = p3d.ClockObject.get_global_clock().get_dt()

        # Adjust the character's z position to stick to the ground
        entries = list(self._char_ground_handler.entries)
        entries.sort(key=lambda x: x.get_surface_point(base.render).get_z())

        for entry in entries:
            if entry.get_into_node().get_name() == 'terrain':
                self.target.set_z(entry.get_surface_point(base.render).get_z())

        # Update movement
        pos_offset = p3d.LVector3(
            self.move_delta.get_x() * self.MOVE_SPEED * dt,
            self.move_delta.get_y() * self.MOVE_SPEED * dt,
            0
        )
        self.target.set_pos(self.target, pos_offset)

        # Update rotation
        turn_offset = self.turn_delta * self.TURN_SPEED * dt
        self.target.set_h(self.target.get_h() + turn_offset)

        # Pick an appropriate animation
        stopped_moving = (
            self.move_delta.length_squared() == 0 and self.turn_delta == 0 and
            (self._prev_move_delta.length_squared() != 0 or self._prev_turn_delta != 0)
        )

        if stopped_moving:
            # All motion stopped
            self.target.loop('cg.Idle')
        elif self.move_delta.get_y() < 0 and self._prev_move_delta.get_y() == 0:
            # Started moving forward
            self.target.loop('cg.Run')
        elif self.move_delta.get_y() > 0 and self._prev_move_delta.get_y() == 0:
            # Started moving backward
            self.target.loop('cg.Run')
            self.target.set_play_rate(-1.0, 'cg.Run')
        elif self.turn_delta != 0 and self._prev_turn_delta == 0 and \
            self.move_delta.length_squared() == 0:
            # Started turning
            self.target.loop('cg.Run')
            self.target.set_play_rate(1.0, 'cg.Run')

        # Save current state for comparisons next frame
        self._prev_move_delta = p3d.LVector2(self.move_delta)
        self._prev_turn_delta = self.turn_delta


class CameraController:
    TURN_SPEED = 20

    def __init__(self, camera, traverser, target, offset=p3d.LVector3(0, 0, 0)):
        self.camera = camera
        self.target = target
        self.offset = offset

        # Use a ray to detect the ground
        self._cam_ground_ray = p3d.CollisionRay()
        self._cam_ground_ray.set_origin(0, 0, 9)
        self._cam_ground_ray.set_direction(0, 0, -1)
        self._cam_ground_col = p3d.CollisionNode('ground_ray')
        self._cam_ground_col.add_solid(self._cam_ground_ray)
        self._cam_ground_col.set_from_collide_mask(p3d.CollideMask.bit(0))
        self._cam_ground_col.set_into_collide_mask(p3d.CollideMask.allOff())
        self._cam_ground_col_np = self.camera.attach_new_node(self._cam_ground_col)
        self._cam_ground_handler = p3d.CollisionHandlerQueue()
        traverser.add_collider(self._cam_ground_col_np, self._cam_ground_handler)

        self.turn_delta = 0

    def update(self):
        dt = p3d.ClockObject.get_global_clock().get_dt()

        # If the camera is too far from the target, move it closer.
        # If the camera is too close to the target, move it farther.
        camvec = self.target.get_pos() - self.camera.get_pos()
        camvec.set_z(0)
        camdist = camvec.length()
        camvec.normalize()
        if camdist > 10.0:
            self.camera.set_pos(self.camera.get_pos() + camvec * (camdist - 10))
            camdist = 10.0
        if camdist < 5.0:
            self.camera.set_pos(self.camera.get_pos() - camvec * (5 - camdist))
            camdist = 5.0

        # Keep the camera at one unit above the terrain,
        # or two units above the target, whichever is greater.
        entries = list(self._cam_ground_handler.entries)
        entries.sort(key=lambda x: x.get_surface_point(base.render).get_z())

        for entry in entries:
            if entry.get_into_node().get_name() == 'terrain':
                self.camera.set_z(entry.get_surface_point(base.render).get_z() + 1.5)
        if self.camera.get_z() < self.target.get_z() + 2.0:
            self.camera.set_z(self.target.get_z() + 2.0)

        # The camera should look in target's direction,
        # but it should also try to stay horizontal, so look a
        # bit above target's head.
        self.camera.look_at(self.target.get_pos() + self.offset)

        # Rotate the camera
        self.camera.set_x(self.camera, self.turn_delta * self.TURN_SPEED * dt)


class GameApp(ShowBase):
    def __init__(self):
        super().__init__(self)
        pman.shim.init(self)
        self.eventmapper = eventmapper.EventMapper()

        self.cTrav = p3d.CollisionTraverser()
        self.accept('quit', sys.exit)

        # Setup render pipeline
        self.set_background_color(0.53, 0.80, 0.92, 1)
        self.render.set_antialias(p3d.AntialiasAttrib.M_auto)
        simplepbr.init()

        # Set up the environment
        self.level = self.loader.load_model('models/terrain.bam')
        self.level.reparent_to(self.render)

        # Pull the level lighting up to affect all models
        for light in self.level.find_all_matches('**/+Light'):
            light.parent.reparent_to(self.render)
            self.render.set_light(light)
        self.level.clear_light()


        # Load a character
        self.actor = Actor('models/clay_golem.bam')
        self.actor.reparent_to(self.render)
        self.actor.set_h(180)

        # Set up the camera controller
        self.disable_mouse()
        self.camera.set_pos(self.actor.get_x(), self.actor.get_y() + 10, 2)
        self.camera_controller = CameraController(
            self.camera, self.cTrav, self.actor, p3d.LVector3(0, 0, 2.0)
        )
        def cam_cont_updt(task):
            self.camera_controller.update()
            return task.cont
        self.task_mgr.add(cam_cont_updt, 'Update Camera')
        def turn_camera(turndir):
            self.camera_controller.turn_delta += turndir
        self.accept('camera-left', turn_camera, [1])
        self.accept('camera-right', turn_camera, [-1])
        self.accept('camera-left-up', turn_camera, [-1])
        self.accept('camera-right-up', turn_camera, [1])

        # Setup the character controller
        self.character_controller = CharacterController(self.actor, self.cTrav)
        def char_cont_updt(task):
            self.character_controller.update()
            return task.cont
        self.task_mgr.add(char_cont_updt, 'Update Character')
        def move(movedir):
            movevec = p3d.LVector2(*movedir)
            self.character_controller.move_delta += movevec
        def turn(turndir):
            self.character_controller.turn_delta += turndir
        self.accept('turn-left', turn, [1])
        self.accept('turn-right', turn, [-1])
        self.accept('move-forward', move, [(0, 1)])
        self.accept('move-backward', move, [(0, -1)])
        self.accept('turn-left-up', turn, [-1])
        self.accept('turn-right-up', turn, [1])
        self.accept('move-forward-up', move, [(0, -1)])
        self.accept('move-backward-up', move, [(0, 1)])

        # Uncomment this line to show a visual representation of the
        # collisions occurring
        #self.cTrav.showCollisions(self.render)


def main():
    app = GameApp()
    app.run()

if __name__ == '__main__':
    main()
