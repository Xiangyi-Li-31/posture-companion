import unittest

from posture_companion.pet import PetPose, activity_action, pet_pose_for_score


class PetStateTests(unittest.TestCase):
    def test_pet_mirrors_score_levels(self) -> None:
        self.assertEqual(pet_pose_for_score(5, 40), PetPose.UPRIGHT)
        self.assertEqual(pet_pose_for_score(25, 40), PetPose.LEANING)
        self.assertEqual(pet_pose_for_score(40, 40), PetPose.SLOUCHED)
        self.assertEqual(pet_pose_for_score(None, 40, False), PetPose.AWAY)

    def test_activity_chooses_matching_animation(self) -> None:
        self.assertEqual(activity_action("起身接一杯水"), "drink")
        self.assertEqual(activity_action("做肩颈操 10 分钟"), "stretch")


if __name__ == "__main__":
    unittest.main()
