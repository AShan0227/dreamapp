<script setup lang="ts">
import { onLaunch } from "@dcloudio/uni-app";
import { getAuthToken, getMe } from "./api/dream";

onLaunch(async () => {
  console.log("DreamApp launched");
  // If there's a token, check it's still valid. If not, the API layer
  // auto-clears it and redirects to the auth page on the first 401.
  // First-time visitors land on the home tab and get redirected to auth
  // when they try to do anything authenticated.
  if (getAuthToken()) {
    try {
      await getMe();
    } catch {
      // Token was bad; the 401 handler already cleared it and redirected.
    }
  }
});
</script>
<style lang="scss">
@import './styles/design-tokens.scss';
@import './styles/components.scss';

page {
  background-color: var(--dream-bg-primary);
  color: var(--dream-text-primary);
  font-family: var(--dream-font-sans);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>
